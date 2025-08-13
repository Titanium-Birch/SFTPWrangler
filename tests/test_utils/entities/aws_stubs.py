from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Tuple

from botocore.stub import Stubber
from dataclasses_json import DataClassJsonMixin

from entities.context_under_test import ContextUnderTest
from utils.metrics import LocalMetricClient, MetricClient


@dataclass
class SsmBehaviour(DataClassJsonMixin):
    secret_key_value: Optional[Tuple[str, str]] = None
    custom: Optional[Callable[[Stubber], None]] = None


class AwsStubs:
    s3: Stubber
    ssm: Stubber
    secretsmanager: Stubber

    def test_context(self, current_datetime: Optional[datetime] = None, metric_client: MetricClient = LocalMetricClient()) -> ContextUnderTest:
        return ContextUnderTest(
            ssm_client=self.ssm.client,
            s3_client=self.s3.client,
            secretsmanager_client=self.secretsmanager.client,
            metric_client=metric_client,
            current_datetime=lambda: current_datetime
        )
    
    def setup_ssm(self, behaviour: SsmBehaviour) -> None:
        if behaviour.custom is None and behaviour.secret_key_value is None:
            raise ValueError("Either 'custom' or 'secret_key_value' must be set in SsmBehaviour.")

        if behaviour.custom:
            behaviour.custom(self.ssm)
        elif behaviour.secret_key_value:
            parameter_name, parameter_value = behaviour.secret_key_value
            self.ssm.add_response(
                method='get_parameter',
                expected_params={
                    'Name': parameter_name,
                    'WithDecryption': True
                },
                service_response={
                    'Parameter': {'Value': parameter_value}
                }
            )