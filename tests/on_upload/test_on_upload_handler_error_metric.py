import pytest

from aws_lambda_typing import context as ctx
from botocore.stub import ANY
from datetime import datetime
from on_upload.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from utils.metrics import LocalMetricClient, metric_lambda_execution_error

class Test_On_Upload_Handler_On_Error:

    @pytest.mark.unit
    def test_should_issue_a_lambda_error_metric(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AWS_LAMBDA_LOG_GROUP_NAME", "/aws/lambda/log-group-name")
        invalid_record = {
            "s3": {
                "s3SchemaVersion": "notUsed",
                "configurationId": "notUsed",
                "bucket": {
                    "name": 1234,
                    "ownerIdentity": {
                        "principalId": "notUsed"
                    },
                    "arn": "notUsed"
                },
                "object": {
                    "key": ""
                }
            },
            "eventTime": datetime.now().isoformat()
        } 
        event: S3Event = {"Records": [invalid_record]} # type: ignore       

        context = ctx.Context()
        context.aws_request_id = "abc"

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=context, 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        assert response["statusCode"] == 500
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "log-group-name (abc)", "functionname": "on_upload"})
        ]


