import json
from botocore.exceptions import ClientError
import pytest

from aws_lambda_typing.events import SecretsManagerRotationEvent
from aws_lambda_typing import context as ctx
from requests import HTTPError
from requests_mock import Mocker
from rotate_secrets.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient

ssm_key_softledger_client_credentials = "/softledger/client/credentials"
arn_softledger_auth_token_secret = "arn:aws:secretsmanager:us-east-1:123:secret:prefix/softledger/authentication"

current_datetime = Fixtures.fixed_datetime()

class Test_Rotate_Secrets_Handler_In_Test_Secret_Step:

    @pytest.mark.unit
    def test_gracefully_exit_if_the_AWSPENDING_version_cannot_be_fetched(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SSM_KEY_CLIENT_CREDENTIALS", ssm_key_softledger_client_credentials)
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        client_request_token = "cedb782f-3b2f-4816-b424-3bd7ababda0a"

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": { client_request_token: ["AWSPENDING"] }
            }
        )

        aws_stubs.secretsmanager.add_client_error(
            method='get_secret_value',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'VersionStage': "AWSPENDING"
            },
            service_error_code='ResourceNotFoundException',
            service_message='Specified version not found.',
            http_status_code=404
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="testSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client, current_datetime=current_datetime)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fail_if_pending_auth_token_fails_against_softledger(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SSM_KEY_CLIENT_CREDENTIALS", ssm_key_softledger_client_credentials)
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        client_request_token = "cedb782f-3b2f-4816-b424-3bd7ababda0a"

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": { client_request_token: ["AWSPENDING"] }
            }
        )

        aws_stubs.secretsmanager.add_response(
            method='get_secret_value',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'VersionStage': "AWSPENDING"
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'SecretString': json.dumps(
                    {"access_token": "abc", "expiration": 999999999}
                ),
            }
        )

        requests_mock.get("https://api.softledger.com/v2/webhooks", status_code=403)

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="testSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        with pytest.raises(HTTPError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client, current_datetime=current_datetime)
            )
        aws_stubs.secretsmanager.assert_no_pending_responses()

        assert len(requests_mock.request_history) == 1