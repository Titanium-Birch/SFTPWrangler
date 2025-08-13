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
from utils.crypt import post_process_incoming_file
from utils.metrics import metric_lambda_on_upload

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: S3Event, context: Context, test_context: Optional[ContextUnderTest] = None) -> Dict[str, Any]:
    """Using the specified `s3_event` denoting an object create event from the upload bucket, this function may either
    post process the uploaded object or copy it straight into the incoming bucket.

    Args:
        event (S3Event): s3 event sent when an object is created in the upload bucket
        context (Context): contains AWS Lambda runtime information
        test_context (Optional[ContextUnderTest], optional): may be used in testing for dependency injection

    Returns:
        Dict[str, Any]: summary of the current execution
    """

    logger.info(f"Received event: {event}")

    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    records = event["Records"]

    peer_id: Optional[str] = None
    try:
        s3_client = getattr(test_context, "s3_client", None) or get_s3_client()

        responses = dict()
        for record in records:
            s3_payload: S3 = record["s3"]
            event_time = record["eventTime"]
            bucket = s3_payload["bucket"]
            created_object: S3Object = s3_payload["object"]

            bucket_name = unquote_plus(bucket["name"], encoding="utf-8")
            object_key = unquote_plus(created_object["key"], encoding="utf-8")
            peer_id = object_key.split(sep="/")[0]
            metric_client.rate(metric_name=metric_lambda_on_upload, value=1, tags={"peer": peer_id})

            record_response = post_process_incoming_file(
                s3_client=s3_client,
                ssm_client=ssm_client,
                metric_client=metric_client,
                bucket=bucket_name,
                object_key=object_key,
                object_creation_date=datetime.fromisoformat(event_time),
            )

            for operation_name, bucket_items in record_response.items():
                object_keys = [bucket_item.key for bucket_item in bucket_items]
                if operation_name not in responses:
                    responses[operation_name] = object_keys
                else:
                    responses[operation_name].extend(object_keys)

        return {"statusCode": 200, "headers": {}, "body": responses}
    except Exception as e:
        metric_client.lambda_error(
            execution_id=getattr(context, "aws_request_id", None) or str(uuid.uuid4()),
            function_name="on_upload",
            peer_id=peer_id,
        )

        logger.exception("Lambda (on_upload) failed.")
        return {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": str(e),
            },
        }
