from datetime import datetime
from typing import Any, Dict, Optional
import pytest
from requests_mock import Mocker
from api.api_facade import ArchApiFacade
from api.entities.invoke_api_event import InvokeApiEvent
from utils.metrics import LocalMetricClient
from conftest import BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, BUCKET_NAME_FILES_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client
from api.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from aws_lambda_typing import context as ctx

base_url = ArchApiFacade.ARCH_BASE_URL_PROD

current_datetime = datetime.fromtimestamp(1697203293)
current_year = str(current_datetime.year)

class Test_Api_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_download_entities_from_arch(self, composed_environment: ComposedEnvironment, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        monkeypatch.setenv("BUCKET_NAME_FILES", BUCKET_NAME_FILES_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()        
        
        peer = "marble.arch"
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
            {"name": "B", "resource": "offerings", "limit": 1, "enabled": False},
            {"resource": "tasks", "enabled": True},
        ]}
        peer_config_json = Fixtures.api_peer_config(peer=peer, api_config={"arch": config})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        activities_page_2_url = f"{base_url}/activities?limit=1&offset=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z"
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            json=_multi_page_response(page_num=1, item_count=1, next_page=activities_page_2_url)
        )

        requests_mock.get(
            url=f"{base_url}/activities/{_multipage_item_id(page_num=1, item_num=0)}/files", 
            json={"contents": [
                {"name": "file.txt", "downloadUrl": f"{base_url}/activities/abc/files/txt/download"}
            ]}
        )

        requests_mock.get(
            url=f"{base_url}/activities/abc/files/txt/download", 
            content="== txt content ==".encode("UTF-8")
        )

        activities_page_3_url = f"{base_url}/activities?limit=1&offset=2&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z"
        requests_mock.get(
            url=activities_page_2_url, 
            json=_multi_page_response(page_num=2, item_count=1, next_page=activities_page_3_url)
        )

        requests_mock.get(
            url=f"{base_url}/activities/{_multipage_item_id(page_num=2, item_num=0)}/files", 
            json={"contents": []}
        )

        requests_mock.get(
            url=activities_page_3_url, 
            json=_multi_page_response(page_num=3, item_count=1)
        )

        requests_mock.get(
            url=f"{base_url}/activities/{_multipage_item_id(page_num=3, item_num=0)}/files", 
            json={"contents": []}
        )

        for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
            tasks_page_url = ArchApiFacade.resources_url(resource_name=f"{prefix}_tasks", limit=25, start_time_iso="2023-10-11T23:59:59.999Z", end_time_iso="2023-10-13T00:00:00.000Z")
            requests_mock.get(
                url=tasks_page_url, 
                json=_multi_page_response(page_num=1, item_count=0)
            )        

        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        
        test_context = ContextUnderTest(
            ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )
        response = handler(cloudwatch_event=InvokeApiEvent(id=peer).to_dict(), context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'fetched': [
                    'marble.arch/activities_20231011_235959_to_20231013_000000_1.json',
                    'marble.arch/activities_20231011_235959_to_20231013_000000_2.json',
                    'marble.arch/activities_20231011_235959_to_20231013_000000_3.json'
                ]
            }
        }

def _multi_page_response(page_num: int, item_count: int, next_page: Optional[str] = None) -> Dict[str, Any]:
    contents = []
    for x in range(item_count):
        item = {
            "kind": "activity",
            "selfUrl": "/activities/3121139",
            "id": _multipage_item_id(page_num=page_num, item_num=x),
            "holdingUrl": "/holdings/239297",
            "investingEntityUrl": "/investing-entities/53487",
            "issuingEntityUrl": "/issuing-entities/21875",
            "type": "Capital Call Request",
            "time": "2024-10-22T18:10:34.000Z",
            "createdAt": "2024-10-22T18:11:06.000Z",
            "dueAt": None,
            "statementDate": None,
            "amountCents": None,
            "totalCommitmentCents": None,
            "totalContributionCents": None,
            "remainingCommitmentCents": None,
            "totalDistributionCents": None,
            "recallableDistributionCents": None,
            "capitalAccountCents": None,
            "processedAt": "2024-10-22T18:11:06.000Z"
        }   
        contents.append(item)

    page = {
        "kind": "page",
        "selfUrl": "",
        "contents": contents
    }
    
    if next_page:
        page["next"] = next_page

    return page 

def _multipage_item_id(page_num: int, item_num: int) -> int:
    return page_num * 1000 + item_num
