import logging
import os
import typing
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from botocore.client import BaseClient
from botocore.exceptions import ClientError
from dataclasses_json import DataClassJsonMixin

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

PAGINATOR_DEFAULT_PAGE_SIZE = 1000
DELETE_OBJECTS_CHUNK_SIZE = 1000


@dataclass
class BucketItem(DataClassJsonMixin):
    key: str
    last_modified: Optional[datetime] = field(default=None)


def upload_file(client: BaseClient, bucket_name: str, key: str, data: typing.IO[bytes]) -> BucketItem:
    logger.info(f"About to upload file into S3. Bucket: {bucket_name}, Key: {key}")
    try:
        client.put_object(Bucket=bucket_name, Key=key, Body=data)
        return BucketItem(key=key)
    except ClientError as e:
        logger.exception("Unable to upload file into S3: %s" % (e.response.get("Error", {}).get("Message")))
        raise ValueError("S3 file upload failed.")


def delete_objects(client: BaseClient, bucket_name: str, items: List[BucketItem]) -> None:
    """Deletes the given `items` from the S3 bucket having the specified `bucket_name`. Only a limited
    number items can be deleted at a time, see DELETE_OBJECTS_CHUNK_SIZE.

    Args:
        client (BaseClient): the boto3 client to use for accessing S3
        bucket_name (str): the name of an existing S3 bucket
        items (List[BucketItem]): list of objects in the given bucket which will be removed

    Raises:
        ValueError: if deleting the objects failed or items contains more elements than allowed
    """
    if not items:
        return

    if len(items) > DELETE_OBJECTS_CHUNK_SIZE:
        raise ValueError(f"Unable to delete more than {DELETE_OBJECTS_CHUNK_SIZE} objects at a time.")

    logger.info(f"About to delete {len(items)} in: s3://{bucket_name}")
    delete_statement = {"Objects": [{"Key": item.key} for item in items], "Quiet": False}

    try:
        client.delete_objects(Bucket=bucket_name, Delete=delete_statement)
    except ClientError as e:
        logger.exception("Unable to delete objects: %s" % (e.response.get("Error", {}).get("Message")))
        raise ValueError("Deleting S3 object failed.")


def copy_object(
    client: BaseClient, source_bucket_name: str, source_key: str, destination_bucket_name: str, destination_key: str
) -> BucketItem:
    """Returns a list of items that are contained in the S3 bucket having the specified bucket name.

    Args:
        client (BaseClient): the boto3 client to use for accessing S3
        source_bucket_name (str): the name of an existing S3 bucket acting as the source bucket
        source_key (str): the object key in the source bucket
        destination_bucket_name (str): the name of an existing S3 bucket to which to copy the file to
        destination_key (str): the desired object key in the destination bucket

    Returns:
        BucketItem: the `BucketItem` wrapping the destination item
    """
    logger.info(
        f"About to copy file from: s3://{source_bucket_name}/{source_key} to s3://{destination_bucket_name}/{destination_key}"
    )
    try:
        copy_source = {"Bucket": source_bucket_name, "Key": source_key}
        client.copy_object(CopySource=copy_source, Bucket=destination_bucket_name, Key=destination_key)
        return BucketItem(key=destination_key)
    except ClientError as e:
        logger.exception("Unable to copy file in S3: %s" % (e.response.get("Error", {}).get("Message")))
        raise ValueError("Copying S3 object failed.")


def get_object(client: BaseClient, bucket_name: str, object_key: str) -> typing.BinaryIO:
    """Fetches and returns an existing object from S3.

    Args:
        client (BaseClient): the boto3 client to use for accessing S3
        bucket_name (str): the name of an existing S3 bucket
        object_key (str): the object key in the bucket

    Returns:
        BinaryIO: streaming content of the object
    """
    logger.info(f"About to get object s3://${bucket_name}/{object_key}")
    try:
        return client.get_object(Bucket=bucket_name, Key=object_key)["Body"]
    except ClientError as e:
        logger.exception("Unable to get file from S3: %s" % (e.response.get("Error", {}).get("Message")))
        raise ValueError("Getting S3 object failed.")


def list_bucket(
    client: BaseClient, bucket_name: str, prefix: str = "", page_size: int = PAGINATOR_DEFAULT_PAGE_SIZE
) -> List[BucketItem]:
    """Returns a list of items that are contained in the S3 bucket having the specified bucket name.

    Args:
        client (BaseClient): the boto3 client to use for accessing S3
        bucket_name (str): the name of an existing S3 bucket
        prefix (str, optional): only objects under the specified path prefix will be listed
        page_size (int, optional): number of items to fetch per page. Defaults to PAGINATOR_DEFAULT_PAGE_SIZE.

    Returns:
        List[BucketItem]: complete list of items contained in the bucket
    """
    logger.info(f"About to list all objects in bucket {bucket_name}, fetching {page_size} item(s) per page.")
    try:
        paginator = client.get_paginator("list_objects_v2")

        results = []
        pagination_config = {"PageSize": page_size}
        for i, page in enumerate(
            paginator.paginate(Bucket=bucket_name, Prefix=prefix, PaginationConfig=pagination_config)
        ):
            if page["KeyCount"] == 0:
                logger.info(f"Pagination finished at page {i}. Found {len(results)} object(s).")
                break

            pg_content = page["Contents"]
            results = results + [BucketItem(key=item["Key"], last_modified=item["LastModified"]) for item in pg_content]

        return results
    except ClientError as e:
        logger.exception(
            "Unable to list objects in bucket %s: %s" % (bucket_name, e.response.get("Error", {}).get("Message"))
        )
        raise ValueError("Unable to list existing items in AWS S3.")
