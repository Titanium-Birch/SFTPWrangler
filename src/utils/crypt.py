import io
import logging
import os
import tempfile
import zipfile
from csv import QUOTE_ALL
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import gnupg
from botocore.client import BaseClient

from utils.logs import redacted_pgp_private_key
from utils.metrics import (
    MetricClient,
    SilentMetricClient,
    metric_lambda_on_upload_action,
    metric_lambda_on_upload_files_unzipped,
)
from utils.path_security import validate_safe_filename
from utils.s3 import BucketItem, copy_object, get_object, upload_file
from utils.secrets import fetch_secret

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def pgp_private_key_secret_id(peer_id: str) -> str:
    """Returns the name of a secret in AWS Secrets Manager, which contains the PGP private key
    used to decrypt files that we receive from the specified peer. Note that not all peer's
    may use encryption, hence the secret will exist in AWS but not always contain a value.

    Args:
        peer_id (str): the id of a bank or broker

    Returns:
        str: name of an existing secret in AWS Secrets Manager
    """
    return f"/aws/reference/secretsmanager/lambda/on_upload/pgp/{peer_id}"


def post_process_incoming_file(
    s3_client: BaseClient,
    ssm_client: BaseClient,
    bucket: str,
    object_key: str,
    object_creation_date: datetime,
    metric_client: Optional[MetricClient] = None,
) -> Dict[str, List[BucketItem]]:
    _, file_extension = os.path.splitext(object_key)

    peer_id = object_key.split(sep="/")[0]

    if not metric_client:
        metric_client = SilentMetricClient()

    extension = file_extension.lower()
    metric_client.rate(
        metric_name=metric_lambda_on_upload_action, value=1, tags={"peer": peer_id, "extension": extension}
    )

    match extension:
        case ".zip":
            logger.info(f"Unzipping {object_key}")
            unzipped_items = _unzip_file(s3_client=s3_client, source_bucket=bucket, source_object_key=object_key)
            metric_client.gauge(
                metric_name=metric_lambda_on_upload_files_unzipped, value=len(unzipped_items), tags={"peer": peer_id}
            )
            return {"unzipped": unzipped_items}
        case ".gpg" | ".pgp":
            logger.info(f"Attempting to decrypt {object_key}")
            decrypted_item = _decrypt_file(
                s3_client=s3_client, ssm_client=ssm_client, source_bucket=bucket, source_object_key=object_key
            )
            return {"decrypted": [decrypted_item]}
        case ".xls" | ".xlsx":
            logger.info(f"Converting {object_key} to csv file(s)")
            converted_files = _convert_excel_to_csv(
                s3_client=s3_client, source_bucket=bucket, source_object_key=object_key
            )
            return {"converted": converted_files}

        case _:
            incoming_bucket = os.environ["BUCKET_NAME_INCOMING"]
            logger.info(f"Object {object_key} is ready to get copied into bucket: {incoming_bucket}")
            copied_item = _copy_into_incoming_bucket(
                s3_client=s3_client,
                source_bucket=bucket,
                source_object_key=object_key,
                source_object_creation_date=object_creation_date,
                destination_bucket=incoming_bucket,
            )
            return {"copied": [copied_item]}


def _decrypt_file(
    s3_client: BaseClient, ssm_client: BaseClient, source_bucket: str, source_object_key: str
) -> BucketItem:
    peer_id = source_object_key.split(sep="/")[0]
    secret_id = pgp_private_key_secret_id(peer_id=peer_id)

    pgp_private_key = fetch_secret(client=ssm_client, secret_id=secret_id)
    if not pgp_private_key:
        raise ValueError("You need to configure a PGP private key to process pgp decrypted files.")

    try:
        gnupghome = os.environ.get("GNUPGHOME") or tempfile.mkdtemp()
        logger.info(f"Using gnupghome: {gnupghome}")
        gpg = gnupg.GPG(gnupghome=gnupghome)
        gpg.import_keys(pgp_private_key)

        contents_binary = get_object(client=s3_client, bucket_name=source_bucket, object_key=source_object_key)
        contents = contents_binary.read()
        decrypted = gpg.decrypt(contents, always_trust=True)

        if not decrypted.ok:
            logger.warning(decrypted.problems)
            raise RuntimeError()
    except Exception:
        raise ValueError(
            f"Unable to decrypt file: {source_object_key} using the configured PGP private."
            f"key: {redacted_pgp_private_key(potential_private_key=pgp_private_key)}"
        )

    destination_object_key = ".".join(source_object_key.split(".")[:-1])
    upload_file(client=s3_client, bucket_name=source_bucket, key=destination_object_key, data=BytesIO(decrypted.data))

    return BucketItem(key=destination_object_key)


def _unzip_file(s3_client: BaseClient, source_bucket: str, source_object_key: str) -> List[BucketItem]:
    target_folder = source_object_key.split(sep="/")[:-1]
    zip_file_name, _ = os.path.splitext(source_object_key.split(sep="/")[-1])

    unzipped_items = []

    content = get_object(client=s3_client, bucket_name=source_bucket, object_key=source_object_key)
    buffer = BytesIO(content.read())

    try:
        z = zipfile.ZipFile(buffer)
        for filename in z.namelist():
            try:
                # Validate filename for security
                safe_filename = validate_safe_filename(filename)
                target_file = os.path.join(*target_folder, f"{zip_file_name}__{safe_filename}")
                data = z.open(filename)
                upload_file(client=s3_client, bucket_name=source_bucket, key=target_file, data=data)

                unzipped_items.append(BucketItem(key=target_file))
            except ValueError as e:
                # Log and skip malicious files, but continue processing other files
                logger.warning(f"Skipping malicious file in ZIP: {e}")
                continue
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        logger.exception(f"Unable to extract zip file at: s3://{source_bucket}/{source_object_key}")
        raise ValueError("Unable to extract zip file.")

    return unzipped_items


def _convert_excel_to_csv(s3_client: BaseClient, source_bucket: str, source_object_key: str) -> List[BucketItem]:
    content = get_object(client=s3_client, bucket_name=source_bucket, object_key=source_object_key)
    input = BytesIO(content.read())

    base_path, _ = os.path.splitext(source_object_key)

    converted_items = []

    import pandas as pd

    xls_sheets = pd.read_excel(input, sheet_name=None)

    for i, (sheet_name, sheet_data) in enumerate(xls_sheets.items()):
        df = sheet_data.replace("\n", " ", regex=True)

        sheet_suffix = ""
        if sheet_name:
            sheet_suffix = f"_{sheet_name}"
        destination_object_key = f"{base_path}_sheet{i}{sheet_suffix}.csv"

        output = io.BytesIO()
        df.to_csv(output, index=False, escapechar="\\", doublequote=False, quoting=QUOTE_ALL)

        output.seek(0)
        upload_file(client=s3_client, bucket_name=source_bucket, key=destination_object_key, data=output)

        converted_items.append(BucketItem(key=destination_object_key))

    return converted_items


def _copy_into_incoming_bucket(
    s3_client: BaseClient,
    source_bucket: str,
    source_object_key: str,
    source_object_creation_date: datetime,
    destination_bucket: str,
) -> BucketItem:
    peer_id = source_object_key.split(sep="/")[0]
    file_name = os.path.basename(source_object_key)

    creation_year = str(source_object_creation_date.year)

    destination_key = os.path.join(peer_id, creation_year, file_name)
    return copy_object(
        client=s3_client,
        source_bucket_name=source_bucket,
        source_key=source_object_key,
        destination_bucket_name=destination_bucket,
        destination_key=destination_key,
    )
