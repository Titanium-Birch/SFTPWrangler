import json
import logging
import os
import uuid
from base64 import b64decode
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, Optional

from aws_lambda_typing.context import Context
from aws_lambda_typing.events import APIGatewayProxyEventV2
from botocore.client import BaseClient
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from api.api_facade import ArchApiFacade, WiseApiFacade
from api.entities.invoke_api_event import InvokeApiEvent
from api.entities.non_retryable_error import NonRetryableError
from api.entities.wise_event import WiseEvent
from api.utils.datetime_range_calculator import PreviousDayDatetimeRangeCalculator
from clients import get_metric_client, get_s3_client, get_ssm_client
from entities.context_under_test import ContextUnderTest
from utils.common import peer_secret_id
from utils.config import fetch_peers_config
from utils.metrics import MetricClient, metric_lambda_api, metric_lambda_api_event_peer, metric_lambda_api_events
from utils.s3 import upload_file
from utils.secrets import fetch_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def webhook_handler(
    event: APIGatewayProxyEventV2, context: Context, test_context: Optional[ContextUnderTest] = None
) -> Dict[str, Any]:
    logger.info(f"Received event: {event}")

    s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", None) or (lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    try:
        body = event.get("body")
        if not body:
            raise NonRetryableError("Unable to process requests without a body.")

        headers = event.get("headers", {})

        if headers.get("X-Test-Notification") == "true":
            logger.info("Recognized test request. Exiting.")
            return {"statusCode": 200, "headers": {}, "body": "Test"}

        logger.info("Attempting signature validation.")

        if not (signature_sha256 := headers.get("X-Signature-SHA256")):
            logger.warning("Unable to process requests without the 'X-Signature-SHA256' header.")
            raise NonRetryableError("Invalid")

        logger.info(f"SHA256 signature is: {signature_sha256}")

        if os.environ.get("ENVIRONMENT") == "staging":
            logger.info("Using public key of the Wise sandbox.")
            public_key_str = WiseApiFacade.WISE_SANDBOX_PUB
        else:
            public_key_str = WiseApiFacade.WISE_PRODUCTION_PUB

        pub_key = _parse_pkcs8_public_key(public_key_str=public_key_str)
        verified = _verify_signature(public_key=pub_key, message=body, signature=signature_sha256)
        if verified is False:
            logger.warning(f"Signature is invalid: {signature_sha256}")
            raise NonRetryableError("Invalid")

        delivery_id = headers.get("X-Delivery-Id", "")

        _process_webhook_event(
            s3_client=s3_client,
            metric_client=metric_client,
            body=body,
            delivery_id=delivery_id,
            current_datetime=current_datetime,
        )
        return {"statusCode": 200, "headers": {}, "body": "Success"}
    except NonRetryableError as e:
        logger.exception("Unable to process api webhook event.")
        metric_client.lambda_error(
            execution_id=getattr(context, "aws_request_id", None) or str(uuid.uuid4()),
            function_name="api_webhook",
        )
        return {"statusCode": 200, "headers": {}, "body": e.message}
    except Exception:
        logger.exception("Lambda (apiwebhook) failed.")
        return {"statusCode": 500, "headers": {}, "body": "Failure"}


def handler(
    cloudwatch_event: Dict[str, Any], context: Context, test_context: Optional[ContextUnderTest] = None
) -> Dict[str, Any]:
    """Using the specified `cloudwatch_event`, this function makes sure a specific API integration is getting
    executed. Business logic implementing the API integration is executed and will be provided with contextual
    information.

    Args:
        cloudwatch_event (Dict[str, Any]): event payload from AWS Eventbridge
        context (Context): contains AWS Lambda runtime information
        test_context (Optional[TestContext], optional): used in testing for dependency injection. Default: None

    Returns:
        Dict[str, Any]: Summary of the current run
    """
    logger.info(f"Received event: {cloudwatch_event}")

    s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", None) or (lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    peer_id: Optional[str] = None
    try:
        event = InvokeApiEvent.from_dict(cloudwatch_event)
        peer_id = event.id

        metric_client.rate(metric_name=metric_lambda_api, value=1, tags={"peer": peer_id})

        config = fetch_peers_config()
        peer = next(iter([p for p in config if p["id"] == event.id]), None)
        if peer is None:
            logger.warning(f"No peer '{event.id}' configured.")
            raise ValueError(f"Unable to find peer '{event.id}' in configuration.")

        api_config = peer.get("config", {})
        if wise_config := api_config.get("wise"):
            secret_id = peer_secret_id(peer_id=peer_id, method="api")
            peer_secret = json.loads(fetch_secret(client=ssm_client, secret_id=secret_id))
            api_key = peer_secret.get("api_key", "")

            range_calculator = PreviousDayDatetimeRangeCalculator(current_datetime=current_datetime)
            facade = WiseApiFacade(
                s3_client=s3_client,
                peer_id=peer_id,
                api_key=api_key,
                range_calculator=range_calculator,
            )
            files_fetched = facade.execute(config=wise_config)
        elif arch_config := api_config.get("arch"):
            secret_id = ArchApiFacade.arch_peer_access_token_secret_id(peer_id=peer_id)
            rotating_secret = json.loads(fetch_secret(client=ssm_client, secret_id=secret_id))
            access_token = rotating_secret.get("accessToken", "")
            range_calculator = PreviousDayDatetimeRangeCalculator(current_datetime=current_datetime, exclusive=True)
            facade = ArchApiFacade(
                s3_client=s3_client,
                peer_id=peer_id,
                access_token=access_token,
                range_calculator=range_calculator,
            )
            files_fetched = facade.execute(config=arch_config)
        else:
            raise ValueError(f"Unable to find ApiFacade implementation that can handle '{peer_id}'.")

        return {
            "statusCode": 200,
            "headers": {},
            "body": {"fetched": [item.key for item in files_fetched]},
        }
    except Exception as e:
        metric_client.lambda_error(
            execution_id=getattr(context, "aws_request_id", None) or str(uuid.uuid4()),
            function_name="api",
            peer_id=peer_id,
        )

        logger.exception("Lambda (api) failed.")
        return {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": str(e),
            },
        }


def _process_webhook_event(
    s3_client: BaseClient,
    metric_client: MetricClient,
    body: str,
    delivery_id: str,
    current_datetime: Callable[[], datetime],
) -> None:
    metric_client.rate(metric_name=metric_lambda_api_events, value=1, tags={})

    try:
        wise_event = WiseEvent.from_json(body)
    except (KeyError, AttributeError, json.JSONDecodeError):
        raise NonRetryableError("Unable to transform record into a WiseEvent.")
    else:
        _process_wise_event(
            s3_client=s3_client,
            metric_client=metric_client,
            event=wise_event,
            delivery_id=delivery_id,
            current_datetime=current_datetime,
        )


def _process_wise_event(
    s3_client: BaseClient,
    metric_client: MetricClient,
    event: WiseEvent,
    delivery_id: str,
    current_datetime: Callable[[], datetime],
) -> None:
    logger.info(f"Looking up peer from config against Wise event: {event.to_dict()}")
    try:
        profile_id = str(event.data.resource.profile_id)
    except AttributeError:
        raise NonRetryableError("Given WiseEvent was not in the expected format.")

    try:
        resource_id = str(event.data.resource.id)
    except AttributeError:
        logger.warning("Event does not contain a resource id in it's data.")
        resource_id = "_"

    config = fetch_peers_config()
    api_peers = [p for p in config if p["method"] == "api"]
    peer = next(iter([p for p in api_peers if p.get("config", {}).get("wise", {}).get("profile") == profile_id]), None)
    if peer is None:
        raise NonRetryableError(f"Unable to find wise peer using profile '{profile_id}'.")
    else:
        peer_id = peer["id"]
        logger.info(f"Wise event is for peer '{profile_id}'")

        metric_client.rate(metric_name=metric_lambda_api_event_peer, value=1, tags={"peer": peer_id})

        dt = current_datetime()
        suffix = str(int(dt.timestamp()))

        event_type = (event.event_type or "-").replace("#", "-")

        object_key = _assemble_object_key(
            peer_id=peer_id,
            profile=profile_id,
            event_type=event_type,
            id=resource_id,
            suffix=suffix,
        )

        upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]

        event_payload = event.to_dict()
        event_payload["delivery_id"] = delivery_id

        file_contents = json.dumps(event_payload)

        upload_file(
            client=s3_client,
            bucket_name=upload_bucket,
            key=object_key,
            data=BytesIO(file_contents.encode("utf-8")),
        )


def _parse_pkcs8_public_key(public_key_str: str) -> RSAPublicKey:
    public_key_bytes: bytes = public_key_str.encode("utf-8")
    key_types = load_pem_public_key(public_key_bytes)
    if isinstance(key_types, RSAPublicKey):
        return key_types
    else:
        raise ValueError(f"This is not an rsa.RSAPublicKey: {public_key_str}")


def _verify_signature(public_key: RSAPublicKey, message: str, signature: str) -> bool:
    signature_bytes: bytes = b64decode(signature)
    message_bytes: bytes = message.encode("utf-8")

    try:
        public_key.verify(signature_bytes, message_bytes, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def _assemble_object_key(peer_id: str, profile: str, event_type: str, id: str, suffix: str) -> str:
    return f"{peer_id}/{profile}/{event_type}/{id}_{suffix}.json"
