import json
import pytest
from requests_mock import Mocker


from api.app import handler
from aws_lambda_typing import context as ctx
from api.entities.invoke_api_event import InvokeApiEvent
from test_utils.entities.aws_stubs import AwsStubs, SsmBehaviour
from test_utils.fixtures import Fixtures


class Test_Api_Handler:

    @pytest.mark.unit
    def test_should_fail_if_event_schema_is_invalid(self, aws_stubs: AwsStubs):
        invocation_event = {"unexpected": "[invalid]"}
        test_context = aws_stubs.test_context() 

        response = handler(
            cloudwatch_event=invocation_event, context=ctx.Context(), test_context=test_context
        )
        assert response["statusCode"] == 500

    @pytest.mark.unit
    def test_should_fail_if_peer_config_cannot_be_read(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        appconfig_test_url = "http://localhost:2772/applications/foo/environments/bar/configurations/s3"
        monkeypatch.setenv("APP_CONFIG_PEERS_URL", appconfig_test_url)

        requests_mock.get(appconfig_test_url, status_code=400)

        event = InvokeApiEvent(id="something").to_dict()
        test_context = aws_stubs.test_context() 
        response = handler(
            cloudwatch_event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': "Unable to fetch peers config."
            }
        }

    @pytest.mark.unit
    def test_should_fail_if_api_peer_has_no_facade_implemented(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        peer_id = "wise"
        peer_config_json = Fixtures.api_peer_config(peer = peer_id, api_config = {"paypal": {}})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        event = InvokeApiEvent(id=peer_id).to_dict()
        test_context = aws_stubs.test_context() 
        response = handler(
            cloudwatch_event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': f"Unable to find ApiFacade implementation that can handle '{peer_id}'."
            }
        }

    @pytest.mark.unit
    def test_should_fail_if_peer_secret_cannot_be_fetched(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        aws_stubs.setup_ssm(
            SsmBehaviour(
                custom=lambda ssm_stub: ssm_stub.add_client_error(
                    method='get_parameter',
                    service_error_code='ParameterNotFound',
                    service_message='The parameter couldnt be found. Verify the name and try again.',
                    http_status_code=404,
                )
            )
        )

        peer_id = "wise"
        peer_config_json = Fixtures.api_peer_config(peer = peer_id)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        event = InvokeApiEvent(id=peer_id).to_dict()
        test_context = aws_stubs.test_context() 
        response = handler(
            cloudwatch_event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': f"Unable to fetch parameter /aws/reference/secretsmanager/lambda/api/{peer_id} from AWS Secrets Manager."
            }
        }
        aws_stubs.ssm.assert_no_pending_responses()