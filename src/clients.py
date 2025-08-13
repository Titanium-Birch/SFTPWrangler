import logging
import os
from datetime import datetime
from typing import Callable

import boto3
from mypy_boto3_s3 import S3Client
from mypy_boto3_secretsmanager import SecretsManagerClient
from mypy_boto3_ssm import SSMClient

from utils.metrics import LocalMetricClient, MetricClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def get_ssm_client() -> SSMClient:
    return boto3.client("ssm")


def get_s3_client() -> S3Client:
    return boto3.client("s3")


def get_secretsmanager_client() -> SecretsManagerClient:
    return boto3.client("secretsmanager")


def get_metric_client(ssm_client: SSMClient, current_datetime: Callable[[], datetime]) -> MetricClient:
    # todo: how to handle metrics
    return LocalMetricClient()
