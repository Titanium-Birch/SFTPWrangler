import logging
import os
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

from mypy_boto3_s3 import S3Client

from utils.file_transformer import FileTransformer
from utils.metrics import (
    MetricClient,
)
from utils.s3 import copy_object, upload_file

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def peer_secret_id(peer_id: str, method: str = "pull") -> str:
    """Returns the name of a secret in AWS Secrets Manager, which contains relevant secret for the peer having
    the specified peer_id.

    Args:
        peer_id (str): the id of a peer
        method (str): the method that is configured for the peer (default: pull)

    Returns:
        str: name of an existing secret in AWS Secrets Manager
    """
    return f"/aws/reference/secretsmanager/lambda/{method}/{peer_id}"


def attempt_categorisation_and_transformation(
    s3_client: S3Client,
    peer_configured_categories: List[Dict[str, Any]],
    bucket: str,
    object_key: str,
    metric_client: Optional[MetricClient] = None,
) -> List[Dict[str, Any]]:
    """Given a bucket name and an object key, this function attempts to categorise the given file against
    pre-configured set of categories. It also applies any transformations specified in config for the matching
    category.

    Args:
        s3_client (S3Client): the boto client to use with S3
        peer_configured_categories (List): a list of configured categories for the peer that owns the S3 object
        bucket (str): the name of an S3 bucket
        object_key (str): the key of a file object inside the bucket
        metric_client (Optional[MetricClient]): a client for shipping metrics (optional)

    Returns:
        List[Dict[str, Any]]: a summary of how the file object was categorised and whether any transformations were
        applied. if the file was not applicable to any category, an empty list is returned.
    """
    path_elements = object_key.split(sep="/")
    peer_id = path_elements[0]
    # Preserve the path structure after peer_id (could be year, folder, or other structure)
    remaining_path = "/".join(path_elements[1:])
    categorized = []

    file_name = os.path.basename(object_key)
    logger.info(f"Trying to categorize {file_name} against {len(peer_configured_categories)} configuration(s).")

    for category in peer_configured_categories:
        category_id = category["category_id"]
        filename_patterns = category.get("filename_patterns", [])
        logger.info(f"Attempting to match against {len(filename_patterns)} pattern(s) in category: {category_id}")
        for filename_pattern in filename_patterns:
            if re.match(filename_pattern, file_name):
                destination_bucket = os.environ["BUCKET_NAME_CATEGORIZED"]

                file_name = os.path.basename(object_key)
                destination_key = os.path.join(peer_id, category_id, remaining_path)
                transformations_applied = []

                # check if the matching category requires any transformations
                if transformations := category.get("transformations", []):
                    logger.info(f"Applying {len(transformations)} transformation(s) to {file_name}.")

                    # get the file contents
                    file_contents = s3_client.get_object(Bucket=bucket, Key=object_key)
                    file_contents = file_contents["Body"].read().decode("utf-8")

                    # apply all transformations in the order they're specified in config
                    transformed_file_contents = file_contents
                    for file_transformer_cls_name in transformations:
                        logger.info(f"Trying to apply transformation in: {file_transformer_cls_name}")
                        transformer = FileTransformer.create_transformer(file_transformer_cls_name)
                        transformed_file_contents = transformer.transform(csv_content=transformed_file_contents)

                    # write the transformed file to the categorized bucket
                    upload_file(
                        client=s3_client,
                        bucket_name=destination_bucket,
                        key=destination_key,
                        data=BytesIO(transformed_file_contents.encode("utf-8")),
                    )
                    transformations_applied = transformations

                else:
                    # no need to modify the file, so let's just copy it over
                    copy_object(
                        client=s3_client,
                        source_bucket_name=bucket,
                        source_key=object_key,
                        destination_bucket_name=destination_bucket,
                        destination_key=destination_key,
                    )

                categorized.append(
                    {
                        "file_name": file_name,
                        "category_id": category_id,
                        "peer": peer_id,
                        "transformations_applied": transformations_applied,
                    }
                )

    return categorized
