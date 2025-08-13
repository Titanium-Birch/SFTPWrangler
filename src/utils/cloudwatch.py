import logging
import os
from typing import List, Optional
from botocore.client import BaseClient
from dataclasses import dataclass
from botocore.exceptions import ClientError
from dataclasses_json import DataClassJsonMixin

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


@dataclass
class Dimension(DataClassJsonMixin):
    name: str
    value: str


def increment_counter(
    client: BaseClient, namespace: str, name: str, dimensions: Optional[List[Dimension]] = None
) -> None:
    """Increments the counter metric of the given name under the specified namespace by 1. The metric will optionally 
    be recorded using the dimensions sent in by the caller.

    Args:
        client (BaseClient): a cloudwatch client
        namespace (str): the global namespace under which the metric lives
        name (str): the name of the metric
        dimensions (Optional[List[Dimension]], optional): a way to add extra dimensions to the counter metric. Defaults 
        to None.
    """
    logger.info(f"About to increment {name} in namespace {namespace}.")
    metric_dimensions = [{"Name": d.name, "Value": d.value} for d in dimensions or []]
    try:
        client.put_metric_data(
            Namespace=namespace,
            MetricData=[{"MetricName": name, "Dimensions": metric_dimensions, "Unit": "Count", "Value": 1}],
        )
    except ClientError as e:
        logger.exception(
            "Unable to increment %s in namespace %s: %s" % (name, namespace, e.response.get("Error", {}).get("Message"))
        )
