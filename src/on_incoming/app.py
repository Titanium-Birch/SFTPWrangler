import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import unquote_plus

from aws_lambda_typing.context import Context
from aws_lambda_typing.events import S3Event
from aws_lambda_typing.events.s3 import S3, S3Object
from clients import get_metric_client, get_s3_client, get_ssm_client
from entities.context_under_test import ContextUnderTest
from utils.common import attempt_categorisation_and_transformation
from utils.config import fetch_configured_categories

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: S3Event, context: Context, test_context: Optional[ContextUnderTest] = None) -> Dict[str, Any]:
    """Using the specified `s3_event` denoting an object create event from the incoming bucket, this function will
    interpret categorization configs. Only if a file matches a pattern:
    1) copy the object into the appropriate folder in the categorized bucket.
    2) then, and only if specified in config: apply any transformations on the file contents

    Args:
        event (S3Event): s3 event sent when an object is created in the incoming bucket
        context (Context): contains AWS Lambda runtime information
        test_context (Optional[ContextUnderTest], optional): may be used in testing for dependency injection

    Returns:
        Dict[str, Any]: summary of the current execution
    """

    logger.info(f"Received event: {event}")

    # TODO: reduce duplication of these lines with other app.py files?
    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    records = event["Records"]

    peer_id: Optional[str] = None
    try:
        s3_client = getattr(test_context, "s3_client", None) or get_s3_client()

        peer_categories = fetch_configured_categories()

        responses = list()
        for record in records:
            s3_payload: S3 = record["s3"]
            bucket = s3_payload["bucket"]
            created_object: S3Object = s3_payload["object"]

            bucket_name = unquote_plus(bucket["name"], encoding="utf-8")
            object_key = unquote_plus(created_object["key"], encoding="utf-8")

            peer_id = object_key.split(sep="/")[0]
            peer_categories = [category for category in peer_categories if category.get("id") == peer_id]

            responses += attempt_categorisation_and_transformation(
                s3_client=s3_client,
                peer_configured_categories=peer_categories,
                bucket=bucket_name,
                object_key=object_key,
                metric_client=metric_client,
            )

        return {"statusCode": 200, "headers": {}, "body": {"categorized": responses}}
    except Exception as e:
        metric_client.lambda_error(
            execution_id=getattr(context, "aws_request_id", None) or str(uuid.uuid4()), 
            function_name="on_incoming", peer_id=peer_id
        )

        logger.exception("Lambda (on_incoming) failed.")
        return {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": str(e),
            },
        }
