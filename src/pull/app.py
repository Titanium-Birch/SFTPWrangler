import logging
import os
import typing
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from aws_lambda_typing.context import Context
from botocore.client import BaseClient
from dataclasses_json import DataClassJsonMixin
from paramiko import MissingHostKeyPolicy

from clients import get_metric_client, get_s3_client, get_ssm_client
from entities.context_under_test import ContextUnderTest
from pull.entities.sftp_pull_event import SftpPullEvent
from utils.common import peer_secret_id
from utils.config import fetch_peers_config
from utils.logs import redacted_ssh_private_key
from utils.metrics import metric_lambda_pull
from utils.s3 import BucketItem, list_bucket, upload_file
from utils.secrets import fetch_secret
from utils.sftp import (
    FingerprintEnforcingPolicy,
    FingerprintVerificationPolicy,
    SftpFileItem,
    assemble_object_key,
    download_new_files,
    is_useable_private_key,
)

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("paramiko").setLevel(logging.WARNING)


@dataclass
class PullTestContext(DataClassJsonMixin):
    context_under_test: ContextUnderTest
    fingerprint_verification_policy: Optional[FingerprintVerificationPolicy] = field(default=None)


def handler(
    cloudwatch_event: Dict[str, Any], context: Context, pull_test_context: Optional[PullTestContext] = None
) -> Dict[str, Any]:
    """Using the specified `cloudwatch_event`, this function connects to an SFTP, identifies new files and downloads
    them into an S3 bucket.

    Args:
        cloudwatch_event (Dict[str, Any]): event payload from AWS Eventbridge
        context (Context): contains AWS Lambda runtime information
        pull_test_context (Optional[PullTestContext], optional): used in testing for dependency injection. Default: None

    Returns:
        Dict[str, Any]: Summary of the current run
    """
    logger.info(f"Received event: {cloudwatch_event}")

    test_context = getattr(pull_test_context, "context_under_test", None)
    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", None) or (lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    peer_id: Optional[str] = None
    try:
        event = SftpPullEvent.from_dict(cloudwatch_event)

        config = fetch_peers_config()
        peer = next(iter([p for p in config if p["id"] == event.id]), None)
        if peer is None:
            logger.warning(f"No peer '{event.id}' configured.")
            raise ValueError(f"Unable to find peer '{event.id}' in configuration.")

        peer_id = event.id

        sftp_user = peer["username"]
        sftp_host = peer["hostname"]
        sftp_port = peer["port"]
        remote_folder = peer.get("folder", "")
        tag_with_timestamp = peer.get("add-timestamp-to-downloaded-files", False)
        fingerprints = peer.get("host-sha256-fingerprints", [])
        if not fingerprints:
            logger.warning(
                f"⚠️  SECURITY WARNING: No host fingerprints configured for peer '{peer_id}'. "
                f"This allows connections to any server claiming to be '{sftp_host}' and is "
                f"vulnerable to man-in-the-middle attacks. Configure 'host-sha256-fingerprints' "
                f"for production deployments."
            )

        s3_client = getattr(test_context, "s3_client", None) or get_s3_client()
        fingerprint_verification_policy = getattr(
            pull_test_context, "fingerprint_verification_policy", None
        ) or FingerprintEnforcingPolicy(peer_id=peer_id, allowed_fingerprints=fingerprints)

        metric_client.rate(metric_name=metric_lambda_pull, value=1, tags={"peer": event.id})

        # get all previously downloaded files for this peer from the "upload" bucket
        upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]
        previously_downloaded_items = _list_previously_downloaded_items(
            s3_client=s3_client, peer_id=peer_id, bucket_name=upload_bucket
        )
        previously_imported_file_names = {os.path.basename(f.key): f for f in previously_downloaded_items}

        # fetch private key from secretsmanager
        secret_id = peer_secret_id(peer_id=event.id)
        ssh_private_key = fetch_secret(client=ssm_client, secret_id=secret_id)
        if not is_useable_private_key(input=ssh_private_key):
            logger.info(f"Unusable private key: {redacted_ssh_private_key(ssh_private_key)}")
            raise ValueError(
                f"You must enter a valid private key into the Secrets Manager secret: {secret_id}. Skipping attempt."
            )

        def is_new_file(sftp_item: SftpFileItem) -> bool:
            """Callback to check if SFTP file shall be downloaded"""
            return sftp_item.filename not in previously_imported_file_names

        def send_to_upload_bucket(sftp_file_item: SftpFileItem, file_content: typing.BinaryIO) -> None:
            """Uploads the file into S3"""
            object_key = assemble_object_key(
                peer_id=peer_id,
                timestamp_tagging=tag_with_timestamp,
                current_datetime=current_datetime,
                sftp_file_item=sftp_file_item,
            )
            logger.debug(f"Using the following S3 object key: {object_key}")
            upload_file(client=s3_client, bucket_name=upload_bucket, key=object_key, data=file_content)

        downloaded_files = _download_new_sftp_files(
            sftp_user=sftp_user,
            sftp_host=sftp_host,
            sftp_port=sftp_port,
            ssh_private_key=ssh_private_key,
            remote_folder=remote_folder,
            download_eligable=is_new_file,
            download_handler=send_to_upload_bucket,
            missing_host_key_policy=fingerprint_verification_policy,
        )

        return {
            "statusCode": 200,
            "headers": {},
            "body": {
                "imported": [f.convert_to_object_key() for f in downloaded_files],
            },
        }
    except Exception as e:
        metric_client.lambda_error(
            execution_id=getattr(context, "aws_request_id", None) or str(uuid.uuid4()),
            function_name="pull",
            peer_id=peer_id,
        )

        logger.exception("Lambda (pull) failed.")
        return {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": str(e),
            },
        }


def _download_new_sftp_files(
    sftp_user: str,
    sftp_host: str,
    sftp_port: int,
    ssh_private_key: str,
    remote_folder: Optional[str],
    download_eligable: Callable[[SftpFileItem], bool],
    download_handler: Callable[[SftpFileItem, typing.BinaryIO], None],
    missing_host_key_policy: Optional[MissingHostKeyPolicy] = None,
) -> List[SftpFileItem]:
    return download_new_files(
        sftp_user=sftp_user,
        sftp_host=sftp_host,
        sftp_port=sftp_port,
        ssh_private_key=ssh_private_key,
        remote_folder=remote_folder,
        download_eligable=download_eligable,
        download_handler=download_handler,
        missing_host_key_policy=missing_host_key_policy,
    )


def _list_previously_downloaded_items(s3_client: BaseClient, peer_id: str, bucket_name: str) -> List[BucketItem]:
    """Returns a list of `BucketItem`s found in the specified S3 bucket for the specified peer.

    Args:
        s3_client (BaseClient): a S3 client
        peer_id (str): the peer to list previously downloaded items for
        bucket_name (str): the name of an existing S3 bucket

    Returns:
        List[BucketItem]:
    """
    items = list_bucket(client=s3_client, bucket_name=bucket_name, prefix=peer_id)
    logger.info(f"Found {len(items)} previously pulled file(s) in {bucket_name}.")
    return items
