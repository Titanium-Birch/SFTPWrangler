import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from aws_lambda_typing.context import Context
from mypy_boto3_s3 import S3Client
from mypy_boto3_ssm import SSMClient

from admin_tasks.entities.backfill_api_arch import BackfillApiArch
from admin_tasks.entities.backfill_api_wise import BackfillApiWise
from admin_tasks.entities.backfill_categories import BackfillCategories
from admin_tasks.entities.backfill_incoming import BackfillIncoming
from api.api_facade import ArchApiFacade, WiseApiFacade
from api.utils.datetime_range_calculator import BackfillDatetimeRangeCalculator
from clients import get_s3_client, get_ssm_client
from entities.context_under_test import ContextUnderTest
from utils.common import attempt_categorisation_and_transformation, peer_secret_id
from utils.config import fetch_configured_categories, fetch_peers_config
from utils.crypt import post_process_incoming_file
from utils.s3 import DELETE_OBJECTS_CHUNK_SIZE, BucketItem, copy_object, delete_objects, list_bucket
from utils.secrets import fetch_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

MAX_ALLOWED_DATE_RANGE_ARCH = 31


def handler(event: Dict[str, Any], context: Context, test_context: Optional[ContextUnderTest] = None) -> Dict[str, Any]:
    """This functions perform certain admin tasks based on the instructions in the given `AdminTaskEvent`.

    Args:
        event (Dict): event dict containing instructions about the task that shall be performed
        context (Context): contains AWS Lambda runtime information
        test_context (Optional[ContextUnderTest], optional): may be used in testing for dependency injection

    Returns:
        Dict[str, Any]: summary of the current execution
    """

    request_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())
    logger.info(f"Received event: {event} (request id: {request_id})")

    try:
        if event.get("name") == "backfill_categories":
            s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
            try:
                backfill = BackfillCategories.from_dict(event.get("task", {}))
            except KeyError:
                raise ValueError(f"Unable to deserialize BackfillCategories from: {event.get('task', {})}")

            responses = _on_backfill_categories_request(s3_client=s3_client, request_id=request_id, backfill=backfill)
        elif event.get("name") == "backfill_api_wise":
            ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
            s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
            current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())
            try:
                backfill = BackfillApiWise.from_dict(event.get("task", {}))
            except (KeyError, TypeError):
                raise ValueError(f"Unable to deserialize BackfillApiWise from: {event.get('task', {})}")

            responses = _on_backfill_api_wise(
                s3_client=s3_client, ssm_client=ssm_client, current_datetime=current_datetime, backfill=backfill
            )
        elif event.get("name") == "backfill_api_arch":
            ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
            s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
            current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())
            try:
                backfill = BackfillApiArch.from_dict(event.get("task", {}))
            except (KeyError, TypeError):
                raise ValueError(f"Unable to deserialize BackfillApiArch from: {event.get('task', {})}")

            responses = _on_backfill_api_arch(
                s3_client=s3_client, ssm_client=ssm_client, current_datetime=current_datetime, backfill=backfill
            )

        elif event.get("name") == "backfill_incoming":
            ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
            s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
            current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())

            try:
                backfill = BackfillIncoming.from_dict(event.get("task", {}))
            except KeyError:
                raise ValueError(f"Unable to deserialize BackfillIncoming from: {event.get('task', {})}")

            responses = _on_backfill_incoming_request(
                ssm_client=ssm_client,
                s3_client=s3_client,
                backfill=backfill,
                current_datetime=current_datetime,
            )
        else:
            raise ValueError(f"Unsupported AdminTask: {event.get('name')}")

        return {"statusCode": 200, "headers": {}, "body": responses}
    except ValueError as e:
        logger.exception("Exiting.")
        return {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": str(e),
            },
        }


def _satisfies_start_and_end_range(
    item: BucketItem, start_timestamp: Optional[datetime], end_timestamp: Optional[datetime]
) -> bool:
    """Returns True if the specified BucketItem:
     - does not have it's last_modified date attribute populated OR
     - was last modified after the given start_timestamp or start_timestamp is None AND
     - was last modified before the end_timestamp or end_timestamp is None

    :param item: a BucketItem
    :return: boolean
    """
    if item.last_modified is None:
        return True

    if start_timestamp is not None and item.last_modified < start_timestamp:
        return False

    return not (end_timestamp is not None and item.last_modified > end_timestamp)


def _on_backfill_incoming_request(
    ssm_client: SSMClient, s3_client: S3Client, backfill: BackfillIncoming, current_datetime: Callable[[], datetime]
) -> Dict[str, Any]:
    peer_id = backfill.peer_id
    extension = backfill.extension

    start_timestamp = datetime.fromisoformat(backfill.start_timestamp) if (backfill.start_timestamp) else None
    end_timestamp = datetime.fromisoformat(backfill.end_timestamp) if backfill.end_timestamp else None

    def endswith_extension(object_key: str, extension: str) -> bool:
        return os.path.splitext(object_key)[-1] == extension

    upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]
    previously_uploaded = [
        item
        for item in list_bucket(client=s3_client, bucket_name=upload_bucket, prefix=peer_id)
        if endswith_extension(object_key=item.key, extension=extension)
    ]

    responses: Dict[str, List[str]] = dict()

    for bucket_item in previously_uploaded:
        if not bucket_item.last_modified:
            raise ValueError(f"Unable to backfill ({bucket_item.key}) which does not have last modification date set.")

        if not _satisfies_start_and_end_range(
            item=bucket_item, start_timestamp=start_timestamp, end_timestamp=end_timestamp
        ):
            continue

        item_response = post_process_incoming_file(
            s3_client=s3_client,
            ssm_client=ssm_client,
            bucket=upload_bucket,
            object_key=bucket_item.key,
            object_creation_date=bucket_item.last_modified,
        )

        # merge post processing responses
        for process_operation_name, processed_bucket_items in item_response.items():
            object_keys = [item.key for item in processed_bucket_items]
            if process_operation_name in responses:
                responses[process_operation_name] += object_keys
            else:
                responses[process_operation_name] = object_keys

    return responses


def _on_backfill_api_wise(
    s3_client: S3Client, ssm_client: SSMClient, current_datetime: Callable[[], datetime], backfill: BackfillApiWise
) -> Dict[str, Any]:
    peer_id = backfill.peer_id

    logger.info(f"Backfilling wise (api) for {peer_id}")
    if backfill.start_date > backfill.end_date:
        raise ValueError("start_date cannot be after end_date")

    config = fetch_peers_config()
    peer = next(iter([p for p in config if p["id"] == peer_id]), None)
    if peer is None:
        raise ValueError(f"Unable to find peer '{peer_id}' in configuration.")

    files_fetched = []

    api_config = peer.get("config", {})
    if wise_config := api_config.get("wise"):
        secret_id = peer_secret_id(peer_id=peer_id, method="api")
        raw = fetch_secret(client=ssm_client, secret_id=secret_id)
        peer_secret = json.loads(raw)
        api_key = peer_secret.get("api_key", "")

        configured_sub_accounts = wise_config.get("sub_accounts", [])
        if backfill.sub_accounts and any(el not in configured_sub_accounts for el in backfill.sub_accounts):
            raise ValueError("Unable to backfill sub_account that isn't configured.")

        if backfill.sub_accounts is not None:
            # make sure we only backfill requested sub accounts
            wise_config = {**wise_config, "sub_accounts": backfill.sub_accounts}

        range_calculator = BackfillDatetimeRangeCalculator(
            current_datetime=current_datetime, start_date=backfill.start_date, end_date=backfill.end_date
        )
        facade = WiseApiFacade(
            s3_client=s3_client,
            peer_id=peer_id,
            api_key=api_key,
            range_calculator=range_calculator,
        )
        files_fetched = facade.execute(config=wise_config)
    else:
        raise ValueError(f"'{peer_id}' is not properly configured as api peer for wise.")

    return {"fetched": [item.key for item in files_fetched]}


def _on_backfill_api_arch(
    s3_client: S3Client, ssm_client: SSMClient, current_datetime: Callable[[], datetime], backfill: BackfillApiArch
) -> Dict[str, Any]:
    peer_id = backfill.peer_id

    logger.info(f"Backfilling arch (api) for {peer_id}")
    if backfill.start_date > backfill.end_date:
        raise ValueError("start_date cannot be after end_date")
    elif not 0 <= (backfill.end_date - backfill.start_date).days <= MAX_ALLOWED_DATE_RANGE_ARCH:
        raise ValueError(
            f"Expecting a date range between 0 and {MAX_ALLOWED_DATE_RANGE_ARCH} days between start_date and end_date"
        )

    config = fetch_peers_config()
    peer = next(iter([p for p in config if p["id"] == peer_id]), None)
    if peer is None:
        raise ValueError(f"Unable to find peer '{peer_id}' in configuration.")

    files_fetched = []

    api_config = peer.get("config", {})
    if arch_config := api_config.get("arch"):
        if not backfill.entities:
            logger.info("Backfilling all supported entities.")
            backfill_entities = [entity for entity in arch_config.get("entities", []) if entity.get("enabled") is True]
        else:
            backfill_entities = [
                entity
                for entity in arch_config.get("entities", [])
                if entity.get("enabled") is True and entity["resource"] in backfill.entities
            ]

        if not backfill_entities:
            logger.warning(f"Found no entities to be backfilled: {backfill.entities}")
        else:
            secret_id = ArchApiFacade.arch_peer_access_token_secret_id(peer_id=peer_id)
            rotating_secret = json.loads(fetch_secret(client=ssm_client, secret_id=secret_id))
            access_token = rotating_secret.get("accessToken", "")

            arch_backfill_config = {**api_config, "entities": backfill_entities}

            range_calculator = BackfillDatetimeRangeCalculator(
                current_datetime=current_datetime,
                start_date=backfill.start_date,
                end_date=backfill.end_date,
                exclusive=True,
            )
            facade = ArchApiFacade(
                s3_client=s3_client,
                peer_id=peer_id,
                access_token=access_token,
                range_calculator=range_calculator,
            )
            files_fetched = facade.execute(config=arch_backfill_config)
    else:
        raise ValueError(f"'{peer_id}' is not properly configured as api peer for Arch.")

    return {"fetched": [item.key for item in files_fetched]}


def _on_backfill_categories_request(
    s3_client: S3Client, request_id: str, backfill: BackfillCategories
) -> Dict[str, Any]:
    peer_id = backfill.peer_id

    logger.info(f"Backfilling categories for {peer_id}")

    category_id = backfill.category_id
    start_timestamp = datetime.fromisoformat(backfill.start_timestamp) if (backfill.start_timestamp) else None
    end_timestamp = datetime.fromisoformat(backfill.end_timestamp) if backfill.end_timestamp else None

    configured_categories = fetch_configured_categories()
    if not configured_categories:
        logger.warning("You need to configure categories before attempting any categorisation.")
        return {"categorized": []}

    configured_categories = [category for category in configured_categories if category.get("id") == peer_id]

    if category_id:
        logger.info(f"Only category {category_id} will be backfilled ..")
        configured_categories = [
            category for category in configured_categories if category["category_id"] == category_id
        ]

    incoming_bucket = os.environ["BUCKET_NAME_INCOMING"]

    categorized_bucket = os.environ["BUCKET_NAME_CATEGORIZED"]
    previously_categorized = list_bucket(client=s3_client, bucket_name=categorized_bucket, prefix=peer_id)
    chunk_size = DELETE_OBJECTS_CHUNK_SIZE
    chunks = [previously_categorized[i : i + chunk_size] for i in range(0, len(previously_categorized), chunk_size)]
    for items_chunk in chunks:
        if items_chunk:
            # backup the files in the temporary location before deleting them from the 'categorized' bucket
            temp_bucket = os.environ["BUCKET_NAME_BACKFILL_CATEGORIES_TEMP"]
            for deletion_candidate in items_chunk:
                destination_key = os.path.join(request_id, deletion_candidate.key)
                copy_object(
                    client=s3_client,
                    source_bucket_name=categorized_bucket,
                    source_key=deletion_candidate.key,
                    destination_bucket_name=temp_bucket,
                    destination_key=destination_key,
                )

        if category_id:
            # if a single category is backfilled, we only want to delete objects in that category
            category_prefix = os.path.join(peer_id, category_id)
            items_chunk = [bucket_item for bucket_item in items_chunk if bucket_item.key.startswith(category_prefix)]

        delete_objects(client=s3_client, bucket_name=categorized_bucket, items=items_chunk)

    bucket_items = list_bucket(client=s3_client, bucket_name=incoming_bucket, prefix=peer_id)
    bucket_items = [
        item
        for item in bucket_items
        if _satisfies_start_and_end_range(item=item, start_timestamp=start_timestamp, end_timestamp=end_timestamp)
    ]

    responses = list()
    for item in bucket_items:
        object_key = item.key
        responses += attempt_categorisation_and_transformation(
            s3_client=s3_client,
            peer_configured_categories=configured_categories,
            bucket=incoming_bucket,
            object_key=object_key,
        )

    return {"categorized": responses}
