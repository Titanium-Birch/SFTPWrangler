from datetime import datetime, timedelta
from botocore.stub import ANY
import pytest
from requests_mock import Mocker

from admin_tasks.app import MAX_ALLOWED_DATE_RANGE_ARCH, handler
from aws_lambda_typing import context as ctx
from api.api_facade import ArchApiFacade
from test_utils.entities.aws_stubs import AwsStubs, SsmBehaviour
from test_utils.fixtures import Fixtures

from entities.context_under_test import ContextUnderTest

current_datetime = Fixtures.fixed_datetime()

peer = "bank1"
entity_id = "9007"
upload_bucket_name = "upload"
files_bucket_name = "files"

class Test_Admin_Tasks_Handler_When_Backfilling_Arch:

    @pytest.fixture(autouse=True)
    def set_bucket_names(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", upload_bucket_name)
        monkeypatch.setenv("BUCKET_NAME_FILES", files_bucket_name)

    @pytest.mark.unit
    def test_should_successfully_backfill_arch_peers(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        limit = 15
        arch_config = {
            "arch": {
                "entities": [{"resource": "holdings", "enabled": True}, {"resource": "tasks", "limit": limit, "enabled": True}]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=arch_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/rotate/{peer}/arch/auth", "{\"accessToken\":\"value\"}")
            )
        )

        for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
            url = ArchApiFacade.resources_url(resource_name=f"{prefix}_tasks", limit=limit, start_time_iso="2024-09-16T23:59:59.999Z", end_time_iso="2024-09-18T00:00:00.000Z")
            requests_mock.get(url=url, json=single_page_response)

            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket_name,
                    'Key': ANY,
                    'Body': ANY
                },
                service_response={}
            )

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": "2024-09-17", "end_date": "2024-09-17", "entities": ["tasks"]}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": [
                    f"{peer}/due_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/completed_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/created_tasks_20240916_235959_to_20240918_000000_1.json",
                ]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()



    @pytest.mark.unit
    def test_should_backfill_all_entity_types(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        arch_config = {
            "arch": {
                "entities": [
                    {"resource": "holdings", "enabled": True}, 
                    {"resource": "investing-entities", "enabled": True},
                    {"resource": "issuing-entities", "enabled": True},
                    {"resource": "offerings", "enabled": True},
                    {"resource": "activities", "enabled": True},
                    {"resource": "cash-flows", "enabled": True},
                    {"resource": "tasks", "enabled": True},
                ]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=arch_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/rotate/{peer}/arch/auth", "{\"accessToken\":\"value\"}")
            )
        )

        start = f"2024-09-16T23:59:59.999Z"
        end = f"2024-09-18T00:00:00.000Z"
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="holdings", limit=25), json=single_page_response
        )
        requests_mock.get(
            url=f"{ArchApiFacade.ARCH_BASE_URL_PROD}/holdings/{entity_id}/files", 
            json={"contents": []}
        )
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="investing-entities", limit=25), json=single_page_response
        )
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="issuing-entities", limit=25), json=single_page_response
        )
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="offerings", limit=25), json=single_page_response
        )
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="activities", limit=25, start_time_iso=start, end_time_iso=end), json=single_page_response
        )
        requests_mock.get(
            url=f"{ArchApiFacade.ARCH_BASE_URL_PROD}/activities/{entity_id}/files", 
            json={"contents": []}
        )        
        for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
            for resource in ArchApiFacade.ENTITIES_SUPPORTING_SUB_QUERIES:
                page_url = ArchApiFacade.resources_url(resource_name=f"{prefix}_{resource}", limit=25, start_time_iso=start, end_time_iso=end)
                requests_mock.get(
                    url=page_url, 
                    json=single_page_response
                )  

        for _ in range(11):
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket_name,
                    'Key': ANY,
                    'Body': ANY
                },
                service_response={}
            )

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {
                    "peer_id": peer, 
                    "start_date": "2024-09-17", 
                    "end_date": "2024-09-17", 
                    "entities": ["holdings", "investing-entities", "issuing-entities", "offerings", "activities", "cash-flows", "tasks"]
                }
            },
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": [
                    f"{peer}/holdings_20231013_1.json",
                    f"{peer}/investing-entities_20231013_1.json",
                    f"{peer}/issuing-entities_20231013_1.json",
                    f"{peer}/offerings_20231013_1.json",
                    f"{peer}/activities_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/due_cash-flows_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/completed_cash-flows_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/created_cash-flows_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/due_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/completed_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/created_tasks_20240916_235959_to_20240918_000000_1.json",
                ]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_skip_disabled_entities(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        arch_config = {
            "arch": {
                "entities": [
                    {"resource": "holdings", "enabled": True}, 
                    {"resource": "investing-entities"},
                    {"resource": "activities", "enabled": False},
                    {"resource": "tasks", "enabled": True},
                ]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=arch_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/rotate/{peer}/arch/auth", "{\"accessToken\":\"value\"}")
            )
        )

        start = f"2024-09-16T23:59:59.999Z"
        end = f"2024-09-18T00:00:00.000Z"
        requests_mock.get(
            url=ArchApiFacade.resources_url(resource_name="holdings", limit=25), json=single_page_response
        )
        requests_mock.get(
            url=f"{ArchApiFacade.ARCH_BASE_URL_PROD}/holdings/{entity_id}/files", 
            json={"contents": []}
        )
        for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
            requests_mock.get(
                url=ArchApiFacade.resources_url(resource_name=f"{prefix}_tasks", limit=25, start_time_iso=start, end_time_iso=end), json=single_page_response
            )

        for _ in range(4):
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket_name,
                    'Key': ANY,
                    'Body': ANY
                },
                service_response={}
            )

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {
                    "peer_id": peer, 
                    "start_date": "2024-09-17", 
                    "end_date": "2024-09-17"
                }
            },
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": [
                    f"{peer}/holdings_20231013_1.json",                   
                    f"{peer}/due_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/completed_tasks_20240916_235959_to_20240918_000000_1.json",
                    f"{peer}/created_tasks_20240916_235959_to_20240918_000000_1.json",
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
                event={"name": "backfill_api_arch", "task": task},
                context=context,
                test_context=aws_stubs.test_context()
            )
            assert response["statusCode"] == 500


    @pytest.mark.unit
    def test_should_fail_if_date_range_is_too_large(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer=peer, api_config={"arch": {"entities": [{"resource": "holdings", "enabled": True}]}})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        start_date = "2024-09-18"
        end_date = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=MAX_ALLOWED_DATE_RANGE_ARCH + 1)

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": start_date, "end_date": end_date.strftime("%Y-%m-%d")}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": f"Expecting a date range between 0 and {MAX_ALLOWED_DATE_RANGE_ARCH} days between start_date and end_date"}
        }


    @pytest.mark.unit
    def test_should_fail_if_peer_is_unknown(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer="xyz", api_config={"arch": {"entities": []}})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": "Unable to find peer 'bank1' in configuration."}
        }

    @pytest.mark.unit
    def test_should_fail_if_peer_is_not_an_arch_peer(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config={"paypal": {}})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18"}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": "'bank1' is not properly configured as api peer for Arch."}
        }


    @pytest.mark.unit
    def test_should_not_backfill_unknown_and_disabled_entities(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        context = ctx.Context()

        api_config = {
            "arch": {
                "entities": [{"resource": "holdings", "enabled": False}, {"resource": "tasks", "enabled": True}]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=api_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {
                    "peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18", "entities": ["holdings", "offerings"]
                }
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "fetched": []
            }
        }


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

        api_config = {
            "arch": {
                "entities": [{"resource": "holdings", "enabled": False}, {"resource": "tasks", "enabled": True}]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=api_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18", "entities": ["tasks"]}
            },
            context=context,
            test_context=aws_stubs.test_context()
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": f"Unable to fetch parameter /aws/reference/secretsmanager/lambda/rotate/{peer}/arch/auth from AWS Secrets Manager."}
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fail_if_secret_is_invalid(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        api_config = {
            "arch": {
                "entities": [{"resource": "holdings", "enabled": False}, {"resource": "tasks", "enabled": True}]
            }
        }

        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config=api_config)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        context = ctx.Context()

        aws_stubs.setup_ssm(
            SsmBehaviour(
                secret_key_value=(f"/aws/reference/secretsmanager/lambda/rotate/{peer}/arch/auth", "{ foo")
            )
        )

        response = handler(
            event={
                "name": "backfill_api_arch", 
                "task": {"peer_id": peer, "start_date": "2024-09-18", "end_date": "2024-09-18", "entities": ["tasks"]}
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


single_page_response = {
  "kind": "page",
  "selfUrl": "/tasks",
  "contents": [
    {
      "id": entity_id,
      "dueDate": "2023-07-14",
      "completionDate": "2024-04-02",
      "completed": True,
      "creationTime": "2024-03-11T14:13:29.000Z",
      "investorNotes": "This is a note",
      "holdingUrl": "/holdings/16",
      "investingEntityUrl": "/investing-entities/3",
      "activityUrl": "/activities/767801",
      "completedByUserUrl": "/users/2766",
      "assignedToUserUrl": "/users/2766",
      "value": {
        "quantity": 100000,
        "currencyCode": "USD",
        "dollars": 100000
      }
    }
  ],
}

