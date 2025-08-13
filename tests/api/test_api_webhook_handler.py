from io import BytesIO
import json
import pytest


from api.app import webhook_handler
from aws_lambda_typing import context as ctx
from botocore.stub import ANY
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from test_utils.matchers import SameJsonPayload
from utils.metrics import LocalMetricClient, metric_lambda_execution_error

current_datetime = Fixtures.fixed_datetime()
sample_event = '{"data":{"resource":{"id":0,"profile_id":0,"type":"balance-account"},"amount":0.01,"currency":"EUR","transaction_type":"credit","occurred_at":"2024-10-13T09:18:07Z"},"subscription_id":"00000000-0000-0000-0000-000000000000","event_type":"balances#update","schema_version":"2.2.0","sent_at":"2024-10-13T09:18:07Z"}'

class Test_Api_Webhook_Handler:

    @pytest.mark.unit
    def test_should_gracefully_handle_invalid_message_bodies(self, aws_stubs: AwsStubs):
        missing_data = Fixtures.create_wise_event().to_dict()
        del missing_data["data"]
        invalid_bodies = ["no json", json.dumps(missing_data)]

        for event_body in invalid_bodies:
            event = Fixtures.create_api_gateway_event(body=event_body)
            metric_client = LocalMetricClient()
            test_context = aws_stubs.test_context(metric_client=metric_client) 

            response = webhook_handler(
                event=event, context=ctx.Context(), test_context=test_context
            )
            assert response == {"statusCode": 200, "headers": {}, "body": "Invalid"}
            assert metric_client.rate_metrics[metric_lambda_execution_error] == [
                (1, {"context": "missing", "functionname": "api_webhook"})
            ]


    @pytest.mark.unit
    def test_should_gracefully_fail_requests_without_bodies(self, aws_stubs: AwsStubs):
        event = Fixtures.create_api_gateway_event(body=None)
        metric_client = LocalMetricClient()
        test_context = aws_stubs.test_context(metric_client=metric_client) 

        response = webhook_handler(
            event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {"statusCode": 200, "headers": {}, "body": "Unable to process requests without a body."}
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "missing", "functionname": "api_webhook"})
        ]


    @pytest.mark.unit
    def test_should_reject_if_signature_is_missing(self, aws_stubs: AwsStubs):
        wise_event = Fixtures.create_wise_event()
        event = Fixtures.create_api_gateway_event(
            body=wise_event.to_json(), headers={"content-type": "application/json"}
        )
        metric_client = LocalMetricClient()
        response = webhook_handler(
            event=event, context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        assert response == {"statusCode": 200, "headers": {}, "body": "Invalid"}
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "missing", "functionname": "api_webhook"})
        ]


    @pytest.mark.unit
    def test_should_reject_if_signature_is_invalid(self, aws_stubs: AwsStubs):
        wise_event = Fixtures.create_wise_event()
        event = Fixtures.create_api_gateway_event(
            body=wise_event.to_json(), 
            headers={
                "content-type": "application/json",
                "X-Signature-SHA256": "abc12345"
            }
        )
        metric_client = LocalMetricClient()
        response = webhook_handler(
            event=event, context=ctx.Context(), 
            test_context=aws_stubs.test_context(metric_client=metric_client)
        )
        assert response == {"statusCode": 200, "headers": {}, "body": "Invalid"}
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "missing", "functionname": "api_webhook"})
        ]


    @pytest.mark.unit
    def test_should_gracefully_handle_missing_peer_configuration(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        peer_id = "wise"
        wise_config = {
            "wise": {
                "profile": "1",
                "sub_accounts": ["123456789"]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer=peer_id, method="api", api_config=wise_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        event = Fixtures.create_api_gateway_event(
            body=sample_event,
            headers={
                "content-type": "application/json",
                "X-Signature-SHA256": "NEYzkdTkGBgKCmWJPT01BdLZJkVcikQDSHP7r+fk7bKyAOXGcwKiPgWWZb1K2PuMeqK6Ye4N+B1hBReV0Q1SWm21MhY1GlcbZg87ZNHWTEwHSHtkAtGnLR3U0IBy/Cyqwk4g31AantPibujBQ4ea42uA0ulcGL3nq9VrIOaJYBFhQvAtSd9Bg17MEeS54dUBV107jRjU7d9adnnFEUbd0GqCktG7OU9qW5JFNPBNPYIyqjtycnxSNKLTbvhMKbKXdp14g4lHb8JSbLMcPGKF2Gta5Nc5AyTUaUqiHsCOrDTdlb43gKe+vIdnWC2xqbBWWCbeP70HK9gDvxwcNK5TQw=="
            }
        )
        metric_client = LocalMetricClient()
        test_context = aws_stubs.test_context(metric_client=metric_client) 

        response = webhook_handler(
            event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {"statusCode": 200, "headers": {}, "body": "Unable to find wise peer using profile '0'."}
        assert metric_client.rate_metrics[metric_lambda_execution_error] == [
            (1, {"context": "missing", "functionname": "api_webhook"})
        ]


    @pytest.mark.unit
    def test_should_throw_if_s3_upload_fails(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        event_json = json.loads(sample_event)
        profile_id = event_json["data"]["resource"]["profile_id"]
        peer_id = "wise"
        wise_config = {
            "wise": {
                "profile": str(profile_id),
                "sub_accounts": ["123456789"]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer=peer_id, method="api", api_config=wise_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        monkeypatch.setenv("BUCKET_NAME_UPLOAD", "upload_bucket")

        event = Fixtures.create_api_gateway_event(
            body=sample_event,
            headers={
                "content-type": "application/json",
                "X-Signature-SHA256": "NEYzkdTkGBgKCmWJPT01BdLZJkVcikQDSHP7r+fk7bKyAOXGcwKiPgWWZb1K2PuMeqK6Ye4N+B1hBReV0Q1SWm21MhY1GlcbZg87ZNHWTEwHSHtkAtGnLR3U0IBy/Cyqwk4g31AantPibujBQ4ea42uA0ulcGL3nq9VrIOaJYBFhQvAtSd9Bg17MEeS54dUBV107jRjU7d9adnnFEUbd0GqCktG7OU9qW5JFNPBNPYIyqjtycnxSNKLTbvhMKbKXdp14g4lHb8JSbLMcPGKF2Gta5Nc5AyTUaUqiHsCOrDTdlb43gKe+vIdnWC2xqbBWWCbeP70HK9gDvxwcNK5TQw=="
            }
        )
        test_context = aws_stubs.test_context(current_datetime=current_datetime) 

        aws_stubs.s3.add_client_error(
            method='put_object',
            service_error_code='ConditionalRequestConflict',
            service_message='A conflicting operation occured.',
            http_status_code=409
        )
       
        
        response = webhook_handler(
            event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {"statusCode": 500, "headers": {}, "body": "Failure"}
        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_successfully_store_wise_events_in_upload_bucket(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        event_json = json.loads(sample_event)
        
        peer_id = "the_peer"
        profile_id = event_json["data"]["resource"]["profile_id"]
        wise_config = {
            "wise": {
                "profile": str(profile_id),
                "sub_accounts": ["123456789"]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer=peer_id, method="api", api_config=wise_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        upload_bucket = "upload_bucket"
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", upload_bucket)

        delivery_id = "8a42425e-50c1-41be-9832-750fbcf1f441"
        event = Fixtures.create_api_gateway_event(
            body=sample_event,
            headers={
                "content-type": "application/json",
                "X-Delivery-Id": delivery_id,
                "X-Signature-SHA256": "NEYzkdTkGBgKCmWJPT01BdLZJkVcikQDSHP7r+fk7bKyAOXGcwKiPgWWZb1K2PuMeqK6Ye4N+B1hBReV0Q1SWm21MhY1GlcbZg87ZNHWTEwHSHtkAtGnLR3U0IBy/Cyqwk4g31AantPibujBQ4ea42uA0ulcGL3nq9VrIOaJYBFhQvAtSd9Bg17MEeS54dUBV107jRjU7d9adnnFEUbd0GqCktG7OU9qW5JFNPBNPYIyqjtycnxSNKLTbvhMKbKXdp14g4lHb8JSbLMcPGKF2Gta5Nc5AyTUaUqiHsCOrDTdlb43gKe+vIdnWC2xqbBWWCbeP70HK9gDvxwcNK5TQw=="
            }
        )
        test_context = aws_stubs.test_context(current_datetime=current_datetime) 

        suffix = int(current_datetime.timestamp())
        expected_key = f"{peer_id}/{profile_id}/balances-update/{event_json["data"]["resource"]["id"]}_{suffix}.json"
        
        modified_sample_event = json.loads(sample_event)
        modified_sample_event['delivery_id'] = delivery_id

        expected_body = BytesIO(json.dumps(modified_sample_event).encode("utf-8"))        
        
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket,
                'Key': expected_key,
                'Body': SameJsonPayload(expected_body)
            },
            service_response={}
        )
       
        response = webhook_handler(
            event=event, context=ctx.Context(), test_context=test_context
        )
        assert response == {"statusCode": 200, "headers": {}, "body": "Success"}
        aws_stubs.s3.assert_no_pending_responses()