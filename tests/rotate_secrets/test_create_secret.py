from datetime import datetime, timedelta
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

class Test_Rotate_Secrets_Handler_In_Create_Secret_Step:

    @pytest.mark.unit
    def test_should_raise_if_the_secret_is_not_rotatable(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId="arn:aws:secretsmanager:us-east-1:123:secret:nonRotable",
            ClientRequestToken="123"
        )
        with pytest.raises(ValueError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )


    @pytest.mark.unit
    def test_should_raise_if_describing_the_secret_fails(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        aws_stubs.secretsmanager.add_client_error(
            method='describe_secret',
            service_error_code='ResourceNotFoundException',
            service_message='The specified secret does not exist.',
            http_status_code=404
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken="123"
        )
        with pytest.raises(ClientError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )
        aws_stubs.secretsmanager.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_exit_if_secret_is_not_rotating(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": False,
                "VersionIdsToStages": {}
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken="123"
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_exit_if_token_is_not_found_in_metadata_versions(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ROTABLE_SECRET_ARN", arn_softledger_auth_token_secret)
        monkeypatch.setenv("ROTATOR_TYPE", "softledger")

        aws_stubs.secretsmanager.add_response(
            method='describe_secret',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret
            },
            service_response={
                "RotationEnabled": True,
                "VersionIdsToStages": {}
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken="123"
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()



    @pytest.mark.unit
    def test_should_exit_if_token_maps_to_current_version(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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
                "VersionIdsToStages": { client_request_token: ["AWSCURRENT"] }
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()

    
    @pytest.mark.unit
    def test_should_exit_if_token_does_not_map_to_pending_version(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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
                "VersionIdsToStages": { client_request_token: ["AWSPREVIOUS"] }
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fail_if_secret_has_no_current_version(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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
                'VersionStage': "AWSCURRENT"
            },
            service_error_code='ResourceNotFoundException',
            service_message='Specified version not found.',
            http_status_code=404
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        with pytest.raises(ClientError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )
        aws_stubs.secretsmanager.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_skip_issuing_a_new_token_if_expiration_is_more_than_a_day_away(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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

        expiration = json.dumps({"expiration": int(datetime.timestamp(current_datetime + timedelta(hours=48)))})
        aws_stubs.secretsmanager.add_response(
            method='get_secret_value',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret,
                'VersionStage': "AWSCURRENT"
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'SecretString': expiration,
            }
        )


        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client, current_datetime=current_datetime)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()
        aws_stubs.ssm.assert_no_pending_responses()



    @pytest.mark.unit
    def test_should_not_create_a_pending_version_if_getting_softledger_client_credentials_fails(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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
                'VersionStage': "AWSCURRENT"
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'SecretString': 'something',
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

        aws_stubs.ssm.add_client_error(
            method='get_parameter',
            expected_params={
                'Name': ssm_key_softledger_client_credentials,
                'WithDecryption': True
            },
            service_error_code='ResourceNotFoundException',
            service_message='Specified version not found.',
            http_status_code=404
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        with pytest.raises(ClientError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )
        aws_stubs.secretsmanager.assert_no_pending_responses()
        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_not_create_a_pending_version_if_softledger_fails_to_issue_an_authentication_token(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
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
                'VersionStage': "AWSCURRENT"
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'SecretString': 'something',
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

        aws_stubs.ssm.add_response(
            method='get_parameter',
            expected_params={
                'Name': ssm_key_softledger_client_credentials,
                'WithDecryption': True
            },
            service_response={
                'Parameter': {
                    'Value': '{"grant_type": "client_credentials", "audience": "audience", "tenantUUID": "tenantUUID", "client_id": "client_id", "client_secret": "client_secret"}'
                }
            }
        )

        requests_mock.post("https://auth.accounting-auth.com/oauth/token", status_code=500)

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        with pytest.raises(HTTPError):
            handler(
                event=event, 
                context=ctx.Context(), 
                test_context=aws_stubs.test_context(metric_client=metric_client)
            )
        aws_stubs.secretsmanager.assert_no_pending_responses()
        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_create_a_pending_version_using_a_new_softledger_authentication_token(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
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
                'VersionStage': "AWSCURRENT"
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
                'SecretString': 'something',
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

        auth_token = {"access_token": "abc", "expires_in": 1000, "scope": "scope"}
        aws_stubs.ssm.add_response(
            method='get_parameter',
            expected_params={
                'Name': ssm_key_softledger_client_credentials,
                'WithDecryption': True
            },
            service_response={
                'Parameter': {
                    'Value': '{"grant_type": "client_credentials", "audience": "audience", "tenantUUID": "tenantUUID", "client_id": "client_id", "client_secret": "client_secret"}'
                }
            }
        )

        requests_mock.post("https://auth.accounting-auth.com/oauth/token", json=auth_token)

        aws_stubs.secretsmanager.add_response(
            method='put_secret_value',
            expected_params={
                'SecretId': arn_softledger_auth_token_secret,
                'ClientRequestToken': client_request_token,
                'SecretString': json.dumps({**auth_token, "expiration": int(current_datetime.timestamp() + 1000)}),
                'VersionStages': ["AWSPENDING"],
            },
            service_response={
                'ARN': arn_softledger_auth_token_secret,
                'VersionId': client_request_token,
            }
        )

        metric_client = LocalMetricClient()
        event = SecretsManagerRotationEvent(
            Step="createSecret",
            SecretId=arn_softledger_auth_token_secret,
            ClientRequestToken=client_request_token
        )

        handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client, current_datetime=current_datetime)
        )
        aws_stubs.secretsmanager.assert_no_pending_responses()
        aws_stubs.ssm.assert_no_pending_responses()

        assert len(requests_mock.request_history) == 1