import json
from botocore.stub import ANY
import pytest
from requests_mock import Mocker

from admin_tasks.app import handler
from aws_lambda_typing import context as ctx
from api.api_facade import WiseApiFacade
from test_utils.entities.aws_stubs import AwsStubs, SsmBehaviour
from test_utils.fixtures import Fixtures

peer = "bank1"

class Test_Admin_Tasks_Handler_When_Backfilling_Wise:

    @pytest.mark.unit
    def test_should_successfully_backfill_wise(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        profile = "wise_profile"
        first_sub_account = "wise_sub_1"
        second_sub_account = "wise_sub_2"
        wise_config = {
            "wise": {
                "profile": profile,
                "sub_accounts": [first_sub_account, second_sub_account]
            }
        }

        upload_bucket = "upload"
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", upload_bucket)

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=wise_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/api/{peer}", json.dumps({'api_key': 'foo'}))
            )
        )

        def url_for_date(date: str, sub_account: str) -> str:
            return f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
                f"?intervalStart={date}T00:00:00.000Z&intervalEnd={date}T23:59:59.999Z&type=COMPACT"

        requests_mock.get(url=url_for_date("2024-09-17", first_sub_account), json=account_statement_response_no_transaction)
        requests_mock.get(url=url_for_date("2024-09-17", second_sub_account), json=account_statement_response_with_transaction)
        requests_mock.get(url=url_for_date("2024-09-18", first_sub_account), json=account_statement_response_with_transaction)
        requests_mock.get(url=url_for_date("2024-09-18", second_sub_account), json=account_statement_response_with_transaction)

        for _ in range(3):  # one response won't be stored due to not having any transactions
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket,
                    'Key': ANY,
                    'Body': ANY
                },
                service_response={}
            )

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-17", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": [
                    'bank1/wise_profile/wise_sub_1_balance_statement_2024-09-18T00:00:00.000Z_2024-09-18T23:59:59.999Z.json',
                    'bank1/wise_profile/wise_sub_2_balance_statement_2024-09-17T00:00:00.000Z_2024-09-17T23:59:59.999Z.json',
                    'bank1/wise_profile/wise_sub_2_balance_statement_2024-09-18T00:00:00.000Z_2024-09-18T23:59:59.999Z.json',
                ]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_successfully_backfill_individual_wise_sub_accounts(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        profile = "wise_profile"
        first_sub_account = "wise_sub_1"
        second_sub_account = "wise_sub_2"
        wise_config = {
            "wise": {
                "profile": profile,
                "sub_accounts": [first_sub_account, second_sub_account]
            }
        }

        upload_bucket = "upload"
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", upload_bucket)

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=wise_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/api/{peer}", json.dumps({'api_key': 'foo'}))
            )
        )

        def url_for_date(date: str, sub_account: str) -> str:
            return f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
                f"?intervalStart={date}T00:00:00.000Z&intervalEnd={date}T23:59:59.999Z&type=COMPACT"

        requests_mock.get(url=url_for_date("2024-09-17", second_sub_account), json=account_statement_response_with_transaction)
        requests_mock.get(url=url_for_date("2024-09-18", second_sub_account), json=account_statement_response_with_transaction)

        for _ in range(2):  # two statements with transactions expected to be stored
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket,
                    'Key': ANY,
                    'Body': ANY
                },
                service_response={}
            )

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-17", "end_date": "2024-09-18", "sub_accounts": [second_sub_account]}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": [
                    'bank1/wise_profile/wise_sub_2_balance_statement_2024-09-17T00:00:00.000Z_2024-09-17T23:59:59.999Z.json',
                    'bank1/wise_profile/wise_sub_2_balance_statement_2024-09-18T00:00:00.000Z_2024-09-18T23:59:59.999Z.json',
                ]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_fail_if_event_payload_is_invalid(self, aws_stubs: AwsStubs):
        context = ctx.Context()

        tasks = [
            "foo",
            {"peer_id": peer},
            {"peer_id": peer, "start_date": "2024-09-18"},
            {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-17"}
        ]

        for task in tasks:
            response = handler(
                event={"name": "backfill_api_wise", "task": task},
                context=context,
                test_context=aws_stubs.test_context()
            )
            assert response["statusCode"] == 500


    @pytest.mark.unit
    def test_should_fail_if_peer_is_unknown(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer = "xyz")
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response["statusCode"] == 500

    @pytest.mark.unit
    def test_should_fail_if_peer_is_not_api_wise_configured(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config={"paypal": {}})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response["statusCode"] == 500


    @pytest.mark.unit
    def test_should_fail_if_given_sub_account_is_not_configured(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/api/{peer}", json.dumps({'api_key': 'foo'}))
            )
        )

        api_config = {
            "wise": {
                "sub_accounts": ["sub_account_name"]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=api_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {
                    "peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18", "sub_accounts": ["unknown_name"]
                }
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": "Unable to backfill sub_account that isn't configured."}
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fail_if_secret_cannot_be_fetched(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
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

        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer = peer)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": f"Unable to fetch parameter /aws/reference/secretsmanager/lambda/api/{peer} from AWS Secrets Manager."}
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fail_if_secret_is_invalid(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        peer_config_json = Fixtures.api_peer_config(peer = peer)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/api/{peer}", "{ foo")
            )
        )

        response = handler(
            event={
                "name": "backfill_api_wise", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )

        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": "Expecting property name enclosed in double quotes: line 1 column 3 (char 2)"}
        }

        aws_stubs.ssm.assert_no_pending_responses()


account_statement_response_with_transaction = {
    "accountHolder": {
        "type": "BUSINESS",
    },
    "issuer": {
        "name": "Wise Europe SA",
    },
    "bankDetails": [
    ],
    "transactions": [
        {
            "type": "DEBIT"
        }
    ],
}

account_statement_response_no_transaction = {
    "accountHolder": {
        "type": "BUSINESS",
    },
    "issuer": {
        "name": "Wise Europe SA",
    },
    "bankDetails": [
    ]
}

