import logging
import os
from typing import Dict, List, Literal, Optional, Tuple

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

metric_lambda_execution_error = "lambda.execution.error"
metric_lambda_pull = "lambda.pull"
metric_lambda_on_upload = "lambda.on_upload"
metric_lambda_on_upload_action = "lambda.on_upload.action"
metric_lambda_on_upload_files_unzipped = "lambda.on_upload.action.zip.files_unzipped"

metric_lambda_rotate_secrets_action = "lambda.rotate_secrets.action"
metric_lambda_rotate_secrets_create = "lambda.rotate_secrets.create"
metric_lambda_rotate_secrets_test = "lambda.rotate_secrets.test"
metric_lambda_rotate_secrets_finish = "lambda.rotate_secrets.finish"
metric_lambda_api = "lambda.api"
metric_lambda_api_events = "lambda.api_events"
metric_lambda_api_event_peer = "lambda.api_event_peer"
metric_lambda_activity_monitor = "lambda.activity_monitor"

metric_transfer_family_auth_errors = "transfer_family.auth_errors"
metric_transfer_family_connected = "transfer_family.connected"


class MetricClient:
    def lambda_error(
        self: "MetricClient",
        execution_id: str,
        function_name: Literal["on_upload", "on_incoming", "pull", "on_log", "rotate_secrets", "api", "api_webhook"],
        peer_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Subclasses must implement this function to submit a metric which can be used to
        trace errors occurring during execution of an AWS Lambda function.

        Args:
            execution_id (str): distinct id which uniquely identifies the error
            function_name (str): short name of the calling function
            peer_id (str): optional, id of a peer that the Lambda was handling
            tags (str): optional, additional tags to be added to the error metric
        """
        pass

    def rate(self: "MetricClient", metric_name: str, value: int, tags: Dict[str, str]) -> None:
        """Subclasses must implement this function to submit a rate metric using the given
        arguments.

        Args:
            metric_name (str): name of the rate metric
            value (int): the numeric metric value
            tags (Dict[str, str]): a set of tags for the metric
        """
        pass

    def gauge(self: "MetricClient", metric_name: str, value: int, tags: Dict[str, str]) -> None:
        """Subclasses must implement this function to submit a gauge metric using the given
        arguments.

        Args:
            metric_name (str): name of the gauge metric
            value (int): a numeric metric value
            tags (Dict[str, str]): a set of tags attached to the metric
        """
        pass


class LocalMetricClient(MetricClient):
    """MetricClient, which stores metrics internally for use in tests."""

    def __init__(self: "LocalMetricClient") -> None:
        super().__init__()
        self.rate_metrics: Dict[str, List[Tuple[int, Dict[str, str]]]] = dict()
        self.gauge_metrics: Dict[str, List[Tuple[int, Dict[str, str]]]] = dict()

    def lambda_error(
        self: "MetricClient",
        execution_id: str,
        function_name: Literal["on_upload", "on_incoming", "pull", "on_log", "rotate_secrets"],
        peer_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        metric_tags = {"context": "missing", "functionname": function_name}
        if log_group := os.environ.get("AWS_LAMBDA_LOG_GROUP_NAME"):
            simple_log_group_name = log_group.split("/")[-1] if "/" in log_group else log_group
            metric_tags["context"] = f"{simple_log_group_name} ({execution_id})"
        if peer_id:
            metric_tags["peer"] = peer_id
        if tags:
            metric_tags.update(tags)
        self.rate(metric_name=metric_lambda_execution_error, value=1, tags=metric_tags)

    def rate(self: "LocalMetricClient", metric_name: str, value: int, tags: Dict[str, str]) -> None:
        metric_values = self.rate_metrics.get(metric_name, [])
        metric_values.append((value, tags))
        self.rate_metrics[metric_name] = metric_values

    def gauge(self: "LocalMetricClient", metric_name: str, value: int, tags: Dict[str, str]) -> None:
        metric_values = self.gauge_metrics.get(metric_name, [])
        metric_values.append((value, tags))
        self.gauge_metrics[metric_name] = metric_values


class SilentMetricClient(MetricClient):
    pass
