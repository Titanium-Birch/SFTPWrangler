import pytest

from aws_lambda_typing.events import SecretsManagerRotationEvent
from aws_lambda_typing import context as ctx
from rotate_secrets.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient, metric_lambda_execution_error

ssm_key_softledger_client_credentials = "/softledger/client/credentials"
arn_softledger_auth_token_secret = "arn:aws:secretsmanager:us-east-1:123:secret:prefix/softledger/authentication"

current_datetime = Fixtures.fixed_datetime()

class Test_Rotate_Secrets_Handler_On_Error:

    @pytest.mark.unit
    def test_should_issue_a_lambda_error_metric(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_LAMBDA_LOG_GROUP_NAME", "/aws/lambda/log-group-name")
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")
        monkeypatch.setenv("ROTATOR_CONTEXT", "staging")

        metric_client = LocalMetricClient()

        context = ctx.Context()
        context.aws_request_id = "def"

        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId="arn:aws:secretsmanager:us-east-1:123:secret:nonRotable",
            ClientRequestToken="123"
        )

        with pytest.raises(ValueError):
            handler(
                event=event, 
                context=context, 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )

        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "log-group-name (def)", "functionname": "rotate_secrets", "rotator_context": "staging"})
        ]
