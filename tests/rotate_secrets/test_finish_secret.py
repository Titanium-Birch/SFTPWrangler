import json
import pytest

from aws_lambda_typing.events import SecretsManagerRotationEvent
from aws_lambda_typing import context as ctx
from rotate_secrets.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient

ssm_key_softledger_client_credentials = "/softledger/client/credentials"
arn_softledger_auth_token_secret = "arn:aws:secretsmanager:us-east-1:123:secret:prefix/softledger/authentication"

current_datetime = Fixtures.fixed_datetime()

class Test_Rotate_Secrets_Handler_In_Finish_Secret_Step:

    @pytest.mark.unit
    def test_gracefully_exit_if_the_AWSPENDING_version_cannot_be_fetched(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SSM_KEY_CLIENT_CREDENTIALS", ssm_key_softledger_client_credentials)
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        client_request_token = "cedb782f-3b2f-4816-b424-3bd7ababda0a"

        # initial describe_secret call
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
            Step="finishSecret",
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
    def test_should_not_update_version_stage_if_AWSCURRENT_is_already_updated(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SSM_KEY_CLIENT_CREDENTIALS", ssm_key_softledger_client_credentials)
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        client_request_token = "cedb782f-3b2f-4816-b424-3bd7ababda0a"

        # initial describe_secret call
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

        # get_secret_value is done to exist a proper AWSPENDING version exist containing a new secret value - which
        # won't be the case if a rotation is run and the expiration attribute tells us we don't have to rotate yet
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

        # second describe_secret call to similate concurrent update
        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": { client_request_token: ["AWSCURRENT"] }
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="finishSecret",
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
    def test_should_promote_AWSPENDING_to_AWSCURRENT(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SSM_KEY_CLIENT_CREDENTIALS", ssm_key_softledger_client_credentials)
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        client_request_token = "cedb782f-3b2f-4816-b424-3bd7ababda0a"
        older_client_request_token = "aaaa843f-1b4f-4816-b424-3bd7ababda0a"

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": { client_request_token: ["AWSPENDING"], older_client_request_token: ["AWSCURRENT"] }
            }
        )

        # get_secret_value is done to exist a proper AWSPENDING version exist containing a new secret value - which
        # won't be the case if a rotation is run and the expiration attribute tells us we don't have to rotate yet
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

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": { client_request_token: ["AWSPENDING"], older_client_request_token: ["AWSCURRENT"] }
            }
        )

        aws_stubs.secretsmanager.add_response(
            method='update_secret_version_stage',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret,
                'VersionStage': "AWSCURRENT",
                'MoveToVersionId': client_request_token,
                'RemoveFromVersionId': older_client_request_token,
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="finishSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client, current_datetime=current_datetime)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()