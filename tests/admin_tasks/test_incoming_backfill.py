import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from aws_lambda_typing import context as ctx

from admin_tasks.app import handler
from admin_tasks.entities.admin_task import AdminTask
from admin_tasks.entities.backfill_incoming import BackfillIncoming
from admin_tasks.test_categorization_backfill import Test_Admin_Tasks_Handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.s3 import PAGINATOR_DEFAULT_PAGE_SIZE

peer = "bank1"

bucket_name_incoming = "incoming_bucket_name"
bucket_name_upload = "upload_bucket_name"

report_csv_filename = "report.csv"
another_report_csv_filename = "report2.csv"
zip_filename = "report.zip"

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


def _assemble_key_for_incoming_bucket(file: str, year: str):
    return f"{peer}/{year}/{os.path.basename(file)}"


class Test_Admin_Tasks_Handler:

    @pytest.mark.unit
    def test_should_successfully_backfill_incoming_files(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        csv_extension = ".csv"
        upload_listing = [
            {
                "Key": f"{peer}/{file_name}",
                "LastModified": current_datetime,
                "ETag": '"3a3c5ca43d2f01dba42314c1ca7e2237"',
                "Size": 1417,
                "StorageClass": "STANDARD",
            }
            for file_name in [report_csv_filename, another_report_csv_filename, zip_filename]
        ]

        self._set_stubs_happy_path(aws_stubs=aws_stubs, extension=csv_extension,
                                   upload_listing=upload_listing)

        payload = BackfillIncoming(peer_id=peer, extension=csv_extension)
        response = handler(
            event=AdminTask(name="backfill_incoming", task=payload).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "copied": [
                    _assemble_key_for_incoming_bucket(file=report_csv_filename, year=current_year),
                    _assemble_key_for_incoming_bucket(
                        file=another_report_csv_filename, year=current_year),
                ]
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_use_last_modified_date_for_determining_the_year_folder(self,
                                                                           aws_stubs: AwsStubs,
                                                                           monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        csv_extension = ".csv"
        last_modified = datetime.fromisoformat("2021-11-30T12:58:14+00:00")
        year_modified = str(last_modified.year)

        upload_listing = [
            {
                "Key": f"{peer}/{file_name}",
                "LastModified": last_modified,
                "ETag": '"3a3c5ca43d2f01dba42314c1ca7e2237"',
                "Size": 1417,
                "StorageClass": "STANDARD",
            }
            for file_name in [report_csv_filename, another_report_csv_filename, zip_filename]
        ]

        self._set_stubs_happy_path(aws_stubs=aws_stubs, extension=csv_extension,
                                   upload_listing=upload_listing)

        payload = BackfillIncoming(peer_id=peer, extension=csv_extension)
        response = handler(
            event=AdminTask(name="backfill_incoming", task=payload).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "copied": [
                    _assemble_key_for_incoming_bucket(file=report_csv_filename, year=year_modified),
                    _assemble_key_for_incoming_bucket(
                        file=another_report_csv_filename, year=year_modified),
                ]
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.parametrize(
        "upload_listing, start_time, end_time, copied_files",
        [(
                [{
                    "Key": f"{peer}/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                "2023-01-04T12:30:00+00:00",
                "2023-01-12T14:00:00+00:00",
                [_assemble_key_for_incoming_bucket(
                    file=f"{'%.2d' % (x + 1)}.csv", year="2023") for x in range(4, 12)]
        ), (
                [{
                    "Key": f"{peer}/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                "2023-01-04T12:30:00+00:00",
                None,
                [_assemble_key_for_incoming_bucket(
                    file=f"{'%.2d' % (x + 1)}.csv", year="2023") for x in range(4, 20)]
        ), (
                [{
                    "Key": f"{peer}/{'%.2d' % (x + 1)}.csv",
                    "LastModified": datetime.fromisoformat(
                        f"2023-01-{'%.2d' % (x + 1)}T12:00:00+00:00"),
                    "ETag": f"3a3c5ca43d2f01dba42314c1ca7e223{x}",
                    "Size": 2000,
                    "StorageClass": "STANDARD",
                } for x in range(20)],
                None,
                "2023-01-12T14:00:00+00:00",
                [_assemble_key_for_incoming_bucket(
                    file=f"{'%.2d' % (x + 1)}.csv", year="2023") for x in range(12)]
        ), ]
    )
    @pytest.mark.unit
    def test_should_backfill_objects_within_date_range_when_specified(self, upload_listing,
                                                                      start_time, end_time,
                                                                      copied_files,
                                                                      aws_stubs: AwsStubs,
                                                                      monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        csv_extension = ".csv"
        self._set_stubs_happy_path(
            aws_stubs=aws_stubs, extension=csv_extension, upload_listing=upload_listing,
            start_time=start_time, end_time=end_time
        )

        payload = BackfillIncoming(peer_id=peer, extension=csv_extension,
                                   start_timestamp=start_time, end_timestamp=end_time)
        response = handler(
            event=AdminTask(name="backfill_incoming", task=payload).to_dict(),
            context=ctx.Context(),
            test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )

        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "copied": copied_files
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @staticmethod
    def _set_stubs_happy_path(aws_stubs: AwsStubs, extension: str,
                              upload_listing: List[Dict[str, Any]], start_time:
            Optional[str] = None, end_time: Optional[str] = None) -> None:
        aws_stubs.s3.add_response(
            method='list_objects_v2',
            expected_params={
                'Bucket': bucket_name_upload,
                'Prefix': peer,

                "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
            },
            service_response={
                "KeyCount": len(upload_listing),
                "Contents": upload_listing
            }
        )

        # for each object in given data, check if it matches the start and end dates
        # and mock copy_object response accordingly
        dt_start: datetime = datetime.fromisoformat(start_time) if start_time else None
        dt_end: datetime = datetime.fromisoformat(end_time) if end_time else None

        for obj in upload_listing:
            source_key = str(obj["Key"])
            last_modified = obj["LastModified"]

            if dt_start and last_modified < dt_start:
                continue

            if dt_end and last_modified > dt_end:
                continue

            if os.path.splitext(source_key)[-1] == extension:
                year = str(datetime.fromisoformat(str(obj["LastModified"])).year)
                destination_key = _assemble_key_for_incoming_bucket(
                    file=os.path.basename(source_key), year=year)
                aws_stubs.s3.add_response(
                    method='copy_object',
                    expected_params={
                        'CopySource': {
                            "Bucket": bucket_name_upload, "Key": source_key
                        },
                        'Bucket': bucket_name_incoming,
                        'Key': destination_key
                    },
                    service_response={}
                )
