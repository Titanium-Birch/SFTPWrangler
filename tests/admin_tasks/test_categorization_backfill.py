import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

import pytest
from aws_lambda_typing import context as ctx
from requests_mock import Mocker

from admin_tasks.app import handler
from admin_tasks.entities.admin_task import AdminTask
from admin_tasks.entities.backfill_categories import BackfillCategories
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.s3 import PAGINATOR_DEFAULT_PAGE_SIZE

peer = "bank1"

bucket_name_incoming = "incoming_bucket_name"
bucket_name_categorized = "categorized_bucket_name"
bucket_name_backfill_categories_temp = "backfill_categories_temp_bucket_name"

category1_id = "deposit_and_st_report"
category2_id = "fixed_income_report"
category1_patterns = ["Deposit and ST_Report_\\d{8}_\\d{6}.csv"]
category2_patterns = ["Fixed_Income_Report_\\d{8}_\\d{6}.csv",
                      "Fixed Income Report_\\d{8}_\\d{6}.csv"]

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_Admin_Tasks_Handler:

    @pytest.mark.unit
    def test_should_successfully_backfill_categories(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns},
                {"category_id": category2_id, "filename_patterns": category2_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        csv_filename = "Deposit and ST_Report_20230927_110018.csv"
        categorize_listing = [{
            "Key": f"{peer}/{category1_id}/{csv_filename}",
            "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
            "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
            "Size": 1417,
            "StorageClass": "STANDARD",
        }
        ]
        incoming_listing = [
            {
                "Key": f"{peer}/2023/{csv_filename}",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
                "Size": 1417,
                "StorageClass": "STANDARD",
            },
            {
                "Key": f"{peer}/2023/Transaction_20231213.csv",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:05+00:00"),
                "ETag": "02bc99343bbdcbdefc9fe691b6f7deaa",
                "Size": 1332,
                "StorageClass": "STANDARD",
            },
        ]

        request_id = str(uuid.uuid4())

        self._set_stubs_happy_path(
            aws_stubs=aws_stubs, request_id=request_id, categorize_listing=categorize_listing,
            incoming_listing=incoming_listing
        )
        self._set_stubs_recategorization(
            aws_stubs=aws_stubs, incoming_listing=incoming_listing,
            category_setup=[(category1_id, category1_patterns), (category2_id, category2_patterns)]
        )

        event = BackfillCategories(peer_id=peer)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "categorized": [
                    {"file_name": csv_filename, "category_id": category1_id, "peer": peer,
                     "transformations_applied": []}]
            }
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.parametrize(
        "incoming_listing, start_time, end_time, categorized_files",
        [(
                [{
                    "Key": f"{peer}/2023/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                "2023-01-04T12:30:00+00:00",
                "2023-01-12T14:00:00+00:00",
                [{
                    "file_name": f"{'%.2d' % (x + 1)}.csv",
                    "category_id": category1_id, "peer": peer,
                    "transformations_applied": []
                } for x in range(4, 12)]
        ), (
                [{
                    "Key": f"{peer}/2023/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                "2023-01-04T12:30:00+00:00",
                None,
                [{
                    "file_name": f"{'%.2d' % (x + 1)}.csv",
                    "category_id": category1_id, "peer": peer,
                    "transformations_applied": []
                } for x in range(4, 20)]
        ), (
                [{
                    "Key": f"{peer}/2023/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                None,
                "2023-01-12T14:00:00+00:00",
                [{
                    "file_name": f"{'%.2d' % (x + 1)}.csv",
                    "category_id": category1_id, "peer": peer,
                    "transformations_applied": []
                } for x in range(12)]
        ), ]
    )
    @pytest.mark.unit
    def test_should_consider_start_and_end_timestamps_when_backfill_categories(self,
                                                                               incoming_listing,
                                                                               start_time, end_time,
                                                                               categorized_files,
                                                                               aws_stubs: AwsStubs,
                                                                               monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        numeric_csv = ["\\d{2}.csv"]
        peer_config_json = Fixtures.peer_config(
            peer=peer, categories=[{"category_id": category1_id, "filename_patterns": numeric_csv}]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        request_id = str(uuid.uuid4())

        self._set_stubs_happy_path(
            aws_stubs=aws_stubs, request_id=request_id, categorize_listing=[],
            incoming_listing=incoming_listing
        )
        self._set_stubs_recategorization(
            aws_stubs=aws_stubs,
            incoming_listing=incoming_listing,
            category_setup=[(category1_id, numeric_csv)],
            start_time=start_time,
            end_time=end_time
        )

        event = BackfillCategories(peer_id=peer, start_timestamp=start_time, end_timestamp=end_time)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "categorized": categorized_files
            }
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_only_backfill_a_single_category_when_specified(self, aws_stubs: AwsStubs,
                                                                   monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns},
                {"category_id": category2_id, "filename_patterns": category2_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        categorized_listing = [
            {
                "Key": f"{peer}/{category1_id}/{current_year}/random_file.csv",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
                "Size": 1417,
                "StorageClass": "STANDARD",
                "ToBeDeleted": False
            },
            {
                "Key": f"{peer}/{category2_id}/{current_year}/random_other_file.csv",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
                "Size": 1417,
                "StorageClass": "STANDARD",
                "ToBeDeleted": True
            }
        ]

        deposity_report_csv = "Deposit and ST_Report_20230927_110018.csv"
        fixed_income_report_csv = "Fixed Income Report_20230927_110115.csv"

        incoming_listing = [
            {
                "Key": f"{peer}/2023/{deposity_report_csv}",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
                "Size": 1417,
                "StorageClass": "STANDARD",
            },
            {
                "Key": f"{peer}/2023/{fixed_income_report_csv}",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:05+00:00"),
                "ETag": "02bc99343bbdcbdefc9fe691b6f7deaa",
                "Size": 1332,
                "StorageClass": "STANDARD",
            },
        ]

        request_id = str(uuid.uuid4())

        self._set_stubs_happy_path(
            aws_stubs=aws_stubs, request_id=request_id, categorize_listing=categorized_listing,
            incoming_listing=incoming_listing
        )
        self._set_stubs_recategorization(
            aws_stubs=aws_stubs, incoming_listing=incoming_listing[1:],
            category_setup=[(category2_id, category2_patterns)]
        )

        event = BackfillCategories(peer_id=peer, category_id=category2_id)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "categorized": [{"file_name": fixed_income_report_csv, "category_id": category2_id,
                                 "peer": peer, "transformations_applied": []}]
            }
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_successfully_backfill_categories_when_no_categories_are_configured(self,
                                                                                       aws_stubs: AwsStubs,
                                                                                       monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", "[]")

        event = BackfillCategories(peer_id=peer)
        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "categorized": []
            }
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_handle_list_errors(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._set_stubs_list_categorize_bucket_failure(aws_stubs=aws_stubs)

        event = BackfillCategories(peer_id=peer)
        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {'message': 'Unable to list existing items in AWS S3.'}
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_handle_delete_errors(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        csv_filename = "Deposit and ST_Report_20230927_110018.csv"
        categorize_listing = [{
            "Key": f"{peer}/{category1_id}/{csv_filename}",
            "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
            "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
            "Size": 1417,
            "StorageClass": "STANDARD",
        }
        ]

        request_id = str(uuid.uuid4())
        self._set_stubs_delete_objects_failure(aws_stubs=aws_stubs, request_id=request_id,
                                               categorize_listing=categorize_listing)

        event = BackfillCategories(peer_id=peer)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {'message': 'Deleting S3 object failed.'}
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_handle_list_incoming_bucket_errors(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        csv_filename = "Deposit and ST_Report_20230927_110018.csv"
        categorize_listing = [{
            "Key": f"{peer}/{category1_id}/{csv_filename}",
            "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
            "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
            "Size": 1417,
            "StorageClass": "STANDARD",
        }
        ]

        request_id = str(uuid.uuid4())
        self._set_stubs_list_incoming_bucket_failure(aws_stubs=aws_stubs, request_id=request_id,
                                                     categorize_listing=categorize_listing)

        event = BackfillCategories(peer_id=peer)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {'message': 'Unable to list existing items in AWS S3.'}
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_handle_get_parameter_errors(self, aws_stubs: AwsStubs, requests_mock: Mocker,
                                                monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        appconfig_test_url = "http://localhost:2772/applications/foo/environments/bar/configurations/s3"
        monkeypatch.setenv("APP_CONFIG_PEERS_URL", appconfig_test_url)

        requests_mock.get(appconfig_test_url, status_code=404)

        event = BackfillCategories(peer_id=peer)
        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {"message": "Unable to fetch peers config."}
        }
        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_handle_copy_errors(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)
        monkeypatch.setenv("BUCKET_NAME_BACKFILL_CATEGORIES_TEMP",
                           bucket_name_backfill_categories_temp)

        peer_config_json = Fixtures.peer_config(
            peer=peer,
            categories=[
                {"category_id": category1_id, "filename_patterns": category1_patterns}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        csv_filename = "Deposit and ST_Report_20230927_110018.csv"
        categorize_listing = [{
            "Key": f"{peer}/{category1_id}/{csv_filename}",
            "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
            "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
            "Size": 1417,
            "StorageClass": "STANDARD",
        }
        ]
        incoming_listing = [
            {
                "Key": f"{peer}/2023/{csv_filename}",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                "ETag": "3a3c5ca43d2f01dba42314c1ca7e2237",
                "Size": 1417,
                "StorageClass": "STANDARD",
            },
            {
                "Key": f"{peer}/2023/Transaction_20231213.csv",
                "LastModified": datetime.fromisoformat("2021-11-30T12:58:05+00:00"),
                "ETag": "02bc99343bbdcbdefc9fe691b6f7deaa",
                "Size": 1332,
                "StorageClass": "STANDARD",
            },
        ]

        request_id = str(uuid.uuid4())
        self._set_stubs_happy_path(
            aws_stubs=aws_stubs, request_id=request_id, categorize_listing=categorize_listing,
            incoming_listing=incoming_listing
        )
        self._set_stubs_copy_failures(aws_stubs=aws_stubs)

        event = BackfillCategories(peer_id=peer)

        context = ctx.Context()
        context.aws_request_id = request_id

        response = handler(
            event=AdminTask(name="backfill_categories", task=event).to_dict(),
            context=context,
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {'message': 'Copying S3 object failed.'}
        }
        aws_stubs.s3.assert_no_pending_responses()

    @staticmethod
    def _set_stubs_happy_path(aws_stubs: AwsStubs, request_id: str,
                              categorize_listing: List[Dict[str, Any]],
                              incoming_listing: List[Dict[str, Any]]) -> None:
        if categorize_listing:
            def filter_listing_keys(item):
                key, _ = item
                return key in {"Key", "LastModified", "ETag", "Size", "StorageClass"}

            list_objects_response = [dict(filter(filter_listing_keys, element.items())) for element
                                     in categorize_listing]

            aws_stubs.s3.add_response(
                method='list_objects_v2',
                expected_params={
                    'Bucket': bucket_name_categorized,
                    'Prefix': peer,

                    "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
                },
                service_response={
                    "KeyCount": len(list_objects_response),
                    "Contents": list_objects_response
                }
            )

            # for each object in given listing, mock copy_object response for the temporary backup
            for obj in categorize_listing:
                source_key = str(obj["Key"])
                destination_key = f"{request_id}/{source_key}"

                aws_stubs.s3.add_response(
                    method='copy_object',
                    expected_params={
                        'CopySource': {
                            "Bucket": bucket_name_categorized, "Key": source_key
                        },
                        'Bucket': bucket_name_backfill_categories_temp,
                        'Key': destination_key
                    },
                    service_response={}
                )

            deletable_objects = [{"Key": str(item["Key"])} for item in categorize_listing if
                                 item.get("ToBeDeleted", True)]

            aws_stubs.s3.add_response(
                method='delete_objects',
                expected_params={
                    'Bucket': bucket_name_categorized,
                    'Delete': {
                        "Objects": deletable_objects,
                        "Quiet": False
                    }
                },
                service_response={
                    'Deleted': deletable_objects,
                    'RequestCharged': 'requester',
                    'Errors': []
                }
            )
        else:
            aws_stubs.s3.add_response(
                method='list_objects_v2',
                expected_params={
                    'Bucket': bucket_name_categorized,
                    'Prefix': peer,

                    "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
                },
                service_response={
                    "KeyCount": 0
                }
            )

        if incoming_listing:
            list_incoming_response = {
                "KeyCount": len(incoming_listing),
                "Contents": incoming_listing
            }
        else:
            list_incoming_response = {
                "KeyCount": 0
            }

        # mocking list responses based on given data
        aws_stubs.s3.add_response(
            method='list_objects_v2',
            expected_params={
                'Bucket': bucket_name_incoming,
                'Prefix': peer,

                "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
            },
            service_response=list_incoming_response
        )

    @staticmethod
    def _set_stubs_recategorization(aws_stubs: AwsStubs, incoming_listing: List[Dict[str, Any]],
                                    category_setup: List[Tuple[str, List[str]]], start_time:
            Optional[str] = None, end_time: Optional[str] = None) -> None:
        # for each object in given data, check if it matches a category, the start and end dates
        # and mock copy_object response accordingly
        dt_start: Optional[datetime] = datetime.fromisoformat(start_time) if start_time else None
        dt_end: Optional[datetime] = datetime.fromisoformat(end_time) if end_time else None

        for obj in incoming_listing:
            source_key = str(obj["Key"])
            last_modified = obj["LastModified"]
            if dt_start and last_modified < dt_start:
                continue

            if dt_end and last_modified > dt_end:
                continue

            file_name = os.path.basename(source_key)

            for category_id, category_patterns in category_setup:
                for category_pattern in category_patterns:
                    if re.match(category_pattern, file_name):
                        destination_key = f"{peer}/{category_id}/{current_year}/{file_name}"

                        aws_stubs.s3.add_response(
                            method='copy_object',
                            expected_params={
                                'CopySource': {
                                    "Bucket": bucket_name_incoming, "Key": source_key
                                },
                                'Bucket': bucket_name_categorized,
                                'Key': destination_key
                            },
                            service_response={}
                        )

    @staticmethod
    def _set_stubs_list_categorize_bucket_failure(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_client_error(
            method='list_objects_v2',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )

    @staticmethod
    def _set_stubs_delete_objects_failure(aws_stubs: AwsStubs, request_id: str,
                                          categorize_listing: List[Dict[str, Any]]) -> None:
        aws_stubs.s3.add_response(
            method='list_objects_v2',
            expected_params={
                'Bucket': bucket_name_categorized,
                'Prefix': peer,

                "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
            },
            service_response={
                "KeyCount": len(categorize_listing),
                "Contents": categorize_listing
            }
        )

        # for each object in given listing, mock copy_object response for the temporary backup
        for obj in categorize_listing:
            source_key = str(obj["Key"])
            destination_key = f"{request_id}/{source_key}"

            aws_stubs.s3.add_response(
                method='copy_object',
                expected_params={
                    'CopySource': {
                        "Bucket": bucket_name_categorized, "Key": source_key
                    },
                    'Bucket': bucket_name_backfill_categories_temp,
                    'Key': destination_key
                },
                service_response={}
            )

        aws_stubs.s3.add_client_error(
            method='delete_objects',
            service_error_code='Conflict',
            service_message='There was a conflict deleting objects.',
            http_status_code=409
        )

    @staticmethod
    def _set_stubs_list_incoming_bucket_failure(aws_stubs: AwsStubs, request_id: str,
                                                categorize_listing: List[Dict[str, Any]]) -> None:
        aws_stubs.s3.add_response(
            method='list_objects_v2',
            expected_params={
                'Bucket': bucket_name_categorized,
                'Prefix': peer,

                "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
            },
            service_response={
                "KeyCount": len(categorize_listing),
                "Contents": categorize_listing
            }
        )

        # for each object in given listing, mock copy_object response for the temporary backup
        for obj in categorize_listing:
            source_key = str(obj["Key"])
            destination_key = f"{request_id}/{source_key}"

            aws_stubs.s3.add_response(
                method='copy_object',
                expected_params={
                    'CopySource': {
                        "Bucket": bucket_name_categorized, "Key": source_key
                    },
                    'Bucket': bucket_name_backfill_categories_temp,
                    'Key': destination_key
                },
                service_response={}
            )

        aws_stubs.s3.add_response(
            method='delete_objects',
            expected_params={
                'Bucket': bucket_name_categorized,
                'Delete': {
                    "Objects": [{"Key": str(item["Key"])} for item in categorize_listing],
                    "Quiet": False
                }
            },
            service_response={
                'Deleted': [{"Key": str(item["Key"])} for item in categorize_listing],
                'RequestCharged': 'requester',
                'Errors': []
            }
        )

        aws_stubs.s3.add_client_error(
            method='list_objects_v2',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )

    @staticmethod
    def _set_stubs_copy_failures(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_client_error(
            method='copy_object',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )
