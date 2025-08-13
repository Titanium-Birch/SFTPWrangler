import pytest
from aws_lambda_typing import context as ctx
from requests_mock import Mocker

from on_incoming.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient, metric_lambda_execution_error

class Test_Pull_Handler_On_Error:

    @pytest.mark.unit
    def test_should_issue_a_lambda_error_metric(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_LAMBDA_LOG_GROUP_NAME", "/aws/lambda/log-group-name")
        metric_client = LocalMetricClient()

        context = ctx.Context()
        context.aws_request_id = "456"

        event = Fixtures.create_s3_event(bucket_name="bucket", object_key="key")

        appconfig_test_url = "url"
        monkeypatch.setenv("APP_CONFIG_PEERS_URL", appconfig_test_url)
        requests_mock.get(appconfig_test_url, status_code=404)

        response = handler(
            event=event, context=context, test_context=aws_stubs.test_context(metric_client=metric_client)
        )

        assert response["statusCode"] == 500
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "log-group-name (456)", "functionname": "on_incoming"})
        ]