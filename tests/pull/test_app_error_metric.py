import pytest
from aws_lambda_typing import context as ctx

from pull.app import PullTestContext, handler
from test_utils.entities.aws_stubs import AwsStubs
from utils.metrics import LocalMetricClient, metric_lambda_execution_error

class Test_Pull_Handler_On_Error:

    @pytest.mark.unit
    def test_should_issue_a_lambda_error_metric(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_LAMBDA_LOG_GROUP_NAME", "/aws/lambda/log-group-name")

        metric_client = LocalMetricClient()
        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context(metric_client=metric_client)           
        )
        context = ctx.Context()
        context.aws_request_id = "123"

        response = handler(
            cloudwatch_event={"unexpected": "attribute"}, context=context, pull_test_context=pull_test_context
        )

        assert response["statusCode"] == 500
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "log-group-name (123)", "functionname": "pull"})
        ]