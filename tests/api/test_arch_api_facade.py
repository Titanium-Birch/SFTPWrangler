from datetime import datetime
from typing import Any, Dict, Optional
from botocore.stub import ANY
import pytest
from requests_mock import Mocker

from api.api_facade import ArchApiFacade
from api.utils.datetime_range_calculator import DatetimeRange, PreviousDayDatetimeRangeCalculator
from test_utils.entities.aws_stubs import AwsStubs
from utils.s3 import BucketItem

current_datetime = datetime.fromtimestamp(1697203293)
current_year = str(current_datetime.year)

entity_id = 3121139
peer_id = "marble_arch"
upload_bucket_name = "upload"
files_bucket_name = "files"

base_url = ArchApiFacade.ARCH_BASE_URL_PROD

class Test_Arch_Api_Facade:

    @pytest.fixture(autouse=True)
    def set_bucket_names(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", upload_bucket_name)
        monkeypatch.setenv("BUCKET_NAME_FILES", files_bucket_name)

    @pytest.mark.unit
    def test_should_fetch_previous_day_entities(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
            {"name": "B", "resource": "offerings", "limit": 1, "enabled": True},
            {"name": "C", "resource": "issuing-entities", "limit": 1, "enabled": False},
            {"resource": "tasks", "enabled": True},
        ]}
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files", 
            json={"contents": []}
        )

        requests_mock.get(
            url=f"{base_url}/offerings?limit=1", 
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/tasks?limit=25&afterDueDate=2023-10-11T23:59:59.999Z&beforeDueDate=2023-10-13T00:00:00.000Z",
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/tasks?limit=25&afterCompletionDate=2023-10-11T23:59:59.999Z&beforeCompletionDate=2023-10-13T00:00:00.000Z",
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/tasks?limit=25&afterCreationTime=2023-10-11T23:59:59.999Z&beforeCreationTime=2023-10-13T00:00:00.000Z",
            json=single_page_response
        )

        key_activities = ArchApiFacade.assemble_entities_in_range_object_key(
            peer_id=peer_id, resource_name="activities",
            range=DatetimeRange(start_time_iso="2023-10-11T23:59:59.999Z", end_time_iso="2023-10-13T00:00:00.000Z"),
            page=1
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_activities,
                'Body': ANY
            },
            service_response={}
        )

        key_offerings = ArchApiFacade.assemble_entities_snapshot_object_key(
            peer_id=peer_id, resource_name="offerings",
            dt=current_datetime,
            page=1
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_offerings,
                'Body': ANY
            },
            service_response={}
        )

        key_tasks = [ArchApiFacade.assemble_entities_in_range_object_key(
            peer_id=peer_id, resource_name=f"{prefix}_tasks",
            range=DatetimeRange(start_time_iso="2023-10-11T23:59:59.999Z", end_time_iso="2023-10-13T00:00:00.000Z"),
            page=1
        ) for prefix in ArchApiFacade.SUB_QUERY_PREFIXES]

        for key_task in key_tasks:
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': upload_bucket_name,
                    'Key': key_task,
                    'Body': ANY
                },
                service_response={}
            )

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == [BucketItem(key=key_activities), BucketItem(key=key_offerings)] + [BucketItem(key=key_task) for key_task in key_tasks]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    @pytest.mark.skip(reason="Disabled due to Arch API error")
    def test_should_fetch_files_at_the_same_time(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-12T00:00:00.000Z&beforeProcessedAt=2023-10-12T23:59:59.999Z", 
            json=single_page_response
        )

        files_response = [
            {"name": "file.pdf", "downloadUrl": f"/activities/{entity_id}/files/pdf/download"},
            {"name": "file.txt", "downloadUrl": f"{base_url}/activities/{entity_id}/files/txt/download"},
        ]
        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files", 
            json={"contents": files_response}
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files/pdf/download", 
            content="== pdf content ==".encode("UTF-8")
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files/txt/download", 
            content="== txt content ==".encode("UTF-8")
        )

        file_keys = []
        datetime_range = DatetimeRange(start_time_iso="2023-10-12T00:00:00.000Z", end_time_iso="2023-10-12T23:59:59.999Z")
        
        key_metadata = ArchApiFacade.assemble_file_metadata_key(
            peer_id=peer_id, resource_name="activities",
            base_name=datetime_range.file_base_name(),
            entity_id=entity_id,
            page=1
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_metadata,
                'Body': ANY
            },
            service_response={}
        )
        
        for file_name in [file["name"] for file in files_response]:
            file_keys.append(ArchApiFacade.assemble_file_object_key(
                peer_id=peer_id, resource_name="activities",
                base_name=datetime_range.file_base_name(),
                page=1, file_name=file_name
            ))

        for file_key in file_keys:
            aws_stubs.s3.add_response(
                method='put_object',
                expected_params={
                    'Bucket': files_bucket_name,
                    'Key': file_key,
                    'Body': ANY
                },
                service_response={}
            )

        key_activities = ArchApiFacade.assemble_entities_in_range_object_key(
            peer_id=peer_id, resource_name="activities",
            range=datetime_range,
            page=1
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_activities,
                'Body': ANY
            },
            service_response={}
        )

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == [BucketItem(key=key_metadata)] + [BucketItem(key=file_key) for file_key in file_keys] + [BucketItem(key=key_activities)]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_rate_limit_when_fetching_previous_day_entities(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            response_list=[
                {"status_code": 429, "headers": {"ratelimit-reset": "10"}},
                {"status_code": 200, "json": {}}
            ]             
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files", 
            json={"contents": []}
        )

        waited = []
        def rate_limit_handler_under_test(seconds: int) -> None:
            waited.append(seconds)

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            ),
            rate_limit_handler=rate_limit_handler_under_test
        )
        facade.execute(config=config)
        assert waited == [10]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    @pytest.mark.skip(reason="Disabled due to Arch API error")
    def test_should_rate_limit_when_fetching_files_list(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-12T00:00:00.000Z&beforeProcessedAt=2023-10-12T23:59:59.999Z", 
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files",
            response_list=[
                {"status_code": 429, "headers": {"ratelimit-reset": "20"}},
                {"status_code": 200, "json": {"contents": [
                    {"name": "file.pdf", "downloadUrl": f"/activities/{entity_id}/files/pdf/download"}
                ]}}
            ]  
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files/pdf/download", 
            content="== pdf content ==".encode("UTF-8")
        )

        datetime_range = DatetimeRange(start_time_iso="2023-10-12T00:00:00.000Z", end_time_iso="2023-10-12T23:59:59.999Z")
        
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': ArchApiFacade.assemble_file_metadata_key(
                    peer_id=peer_id, resource_name="activities",
                    base_name=datetime_range.file_base_name(),
                    entity_id=entity_id,
                    page=1
                ),
                'Body': ANY
            },
            service_response={}
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': files_bucket_name,
                'Key': ArchApiFacade.assemble_file_object_key(
                    peer_id=peer_id, resource_name="activities",
                    base_name=datetime_range.file_base_name(),
                    page=1, file_name="file.pdf"
                ),
                'Body': ANY
            },
            service_response={}
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': ArchApiFacade.assemble_entities_in_range_object_key(
                    peer_id=peer_id, resource_name="activities",
                    range=DatetimeRange(start_time_iso="2023-10-12T00:00:00.000Z", end_time_iso="2023-10-12T23:59:59.999Z"),
                    page=1
                ),
                'Body': ANY
            },
            service_response={}
        )

        waited = []
        def rate_limit_handler_under_test(seconds: int) -> None:
            waited.append(seconds)

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            ),
            rate_limit_handler=rate_limit_handler_under_test
        )
        facade.execute(config=config)
        assert waited == [20]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    @pytest.mark.skip(reason="Disabled due to Arch API error")
    def test_should_rate_limit_when_downloading_files(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}

        start = "2023-10-12T00:00:00.000Z"
        end = "2023-10-12T23:59:59.999Z"
        date_range = DatetimeRange(start_time_iso=start, end_time_iso=end)
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt={start}&beforeProcessedAt={end}", 
            json=single_page_response
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files",
            json={"contents": [
                {"name": "file.pdf", "downloadUrl": f"/activities/{entity_id}/files/pdf/download"},
            ]} 
        )

        requests_mock.get(
            url=f"{base_url}/activities/{entity_id}/files/pdf/download",
            response_list=[
                {"status_code": 429, "headers": {"ratelimit-reset": "899"}},
                {"status_code": 200, "content": "== pdf content ==".encode("UTF-8")}
            ]  
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': ArchApiFacade.assemble_file_metadata_key(
                    peer_id=peer_id, resource_name="activities",
                    base_name=date_range.file_base_name(),
                    entity_id=entity_id,
                    page=1
                ),
                'Body': ANY
            },
            service_response={}
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': files_bucket_name,
                'Key': ArchApiFacade.assemble_file_object_key(
                    peer_id=peer_id, resource_name="activities",
                    base_name=date_range.file_base_name(),
                    page=1, file_name="file.pdf"
                ),
                'Body': ANY
            },
            service_response={}
        )
        
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': ArchApiFacade.assemble_entities_in_range_object_key(
                    peer_id=peer_id, resource_name="activities",
                    range=date_range,
                    page=1
                ),
                'Body': ANY
            },
            service_response={}
        )

        waited = []
        def rate_limit_handler_under_test(seconds: int) -> None:
            waited.append(seconds)

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            ),
            rate_limit_handler=rate_limit_handler_under_test
        )
        facade.execute(config=config)
        assert waited == [899]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_not_rate_limit_when_waiting_for_more_than_15_minutes(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            response_list=[
                {"status_code": 429, "headers": {"ratelimit-reset": "1000"}}
            ]             
        )

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            ),
        )
        with pytest.raises(ValueError):
            facade.execute(config=config)

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_fetch_previous_day_entities_on_two_pages(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True}
        ]}
       
        page_2_url = f"/activities?limit=1&includeSummaries=true&offset=1&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z"
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            json=_multi_page_response(page_num=1, item_count=1, next_page=page_2_url)
        )

        requests_mock.get(
            url=f"{base_url}/activities/{_multipage_item_id(page_num=1, item_num=0)}/files", 
            json={"contents": []}
        )

        requests_mock.get(
            url=f"{base_url}{page_2_url}", 
            json=_multi_page_response(page_num=2, item_count=1)
        )

        requests_mock.get(
            url=f"{base_url}/activities/{_multipage_item_id(page_num=2, item_num=0)}/files", 
            json={"contents": []}
        )

        range = DatetimeRange(start_time_iso="2023-10-11T23:59:59.999Z", end_time_iso="2023-10-13T00:00:00.000Z")
        
        key_1st_page = ArchApiFacade.assemble_entities_in_range_object_key(
            peer_id=peer_id, resource_name="activities",
            range=range, page=1
        )
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_1st_page,
                'Body': ANY
            },
            service_response={}
        )

        key_2nd_page = ArchApiFacade.assemble_entities_in_range_object_key(
            peer_id=peer_id, resource_name="activities",
            range=range, page=2
        )
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': upload_bucket_name,
                'Key': key_2nd_page,
                'Body': ANY
            },
            service_response={}
        )

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == [BucketItem(key=key_1st_page), BucketItem(key=key_2nd_page)]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_not_store_any_files_if_all_entities_are_disabled(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": False},
            {"name": "B", "resource": "offerings", "limit": 1, "enabled": False},
        ]}
       
        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == []

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_not_store_any_files_without_contents(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        config = {"entities": [
            {"name": "A", "resource": "activities", "limit": 1, "enabled": True},
        ]}

        no_contents = dict(single_page_response)
        del no_contents["contents"]
       
        requests_mock.get(
            url=f"{base_url}/activities?limit=1&includeSummaries=true&afterProcessedAt=2023-10-11T23:59:59.999Z&beforeProcessedAt=2023-10-13T00:00:00.000Z",
            json=no_contents
        )

        facade = ArchApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, access_token="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime, exclusive=True
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == []

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_assemble_correct_resource_urls(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        entities_url = ArchApiFacade.resources_url(resource_name="issuing-entities", limit=10)
        assert entities_url == "https://arch.co/client-api/v0/issuing-entities?limit=10"

        start = "2023-10-12T00:00:00.000Z"
        end = "2023-10-12T23:59:59.999Z"
        activities_url = ArchApiFacade.resources_url(resource_name="activities", limit=10, start_time_iso=start, end_time_iso=end)
        assert activities_url == f"https://arch.co/client-api/v0/activities?limit=10&includeSummaries=true&afterProcessedAt={start}&beforeProcessedAt={end}"

        due_cash_flows_url = ArchApiFacade.resources_url(resource_name="due_cash-flows", limit=35, start_time_iso=start, end_time_iso=end)
        assert due_cash_flows_url == f"https://arch.co/client-api/v0/cash-flows?limit=35&includeAllocations=true&afterDueAt={start}&beforeDueAt={end}"

        completed_tasks_url = ArchApiFacade.resources_url(resource_name="completed_tasks", limit=1, start_time_iso=start, end_time_iso=end)
        assert completed_tasks_url == f"https://arch.co/client-api/v0/tasks?limit=1&afterCompletionDate={start}&beforeCompletionDate={end}"
        


def _multi_page_response(page_num: int, item_count: int, next_page: Optional[str] = None) -> Dict[str, Any]:
    contents = []
    for x in range(item_count):
        item = {
            "kind": "activity",
            "selfUrl": f"/activities/{entity_id}",
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


single_page_response = {
  "kind": "page",
  "selfUrl": "",
  "contents": [
    {
      "kind": "activity",
      "selfUrl": f"/activities/{entity_id}",
      "id": entity_id,
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
  ]
}


    
