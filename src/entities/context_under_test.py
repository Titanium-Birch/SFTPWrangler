from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from botocore.client import BaseClient
from dataclasses_json import DataClassJsonMixin
from utils.metrics import MetricClient


@dataclass
class ContextUnderTest(DataClassJsonMixin):
    ssm_client: Optional[BaseClient]
    s3_client: BaseClient
    secretsmanager_client: Optional[BaseClient]
    metric_client: MetricClient
    current_datetime: Optional[Callable[[], Optional[datetime]]] = field(default=None)
