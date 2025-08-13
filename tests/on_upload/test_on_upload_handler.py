import os
from io import BytesIO

import pytest
from aws_lambda_typing import context as ctx
from botocore.stub import ANY

from on_upload.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient, metric_lambda_on_upload

created_csv_object_key = "bank1/folder/test.csv"
created_zip_object_key = "bank1/sample.zip"
unzipped_object_key = "bank1/sample__ZP1.txt"
bucket_name_upload = "upload_bucket_name"
bucket_name_incoming = "incoming_bucket_name"
current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler:

    @pytest.mark.unit
    def test_should_copy_files_into_the_incoming_bucket(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_csv_object_key, event_time=current_datetime.isoformat())
        self._set_stubs_source_exists(aws_stubs=aws_stubs)

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(current_datetime=current_datetime, metric_client=metric_client)
        )
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                "copied": [self._assemble_key_for_incoming_bucket()]
            }
        }

        assert metric_client.rate_metrics[metric_lambda_on_upload] == [
            (1, {"peer": created_csv_object_key.split("/")[0]})
        ]

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_return_error_response_if_copying_files_fails(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_csv_object_key)
        self._set_stubs_copy_failures(aws_stubs=aws_stubs)

        response = handler(
            event=event, context=ctx.Context(), test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": "Copying S3 object failed."
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_unzip_uploaded_files(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_zip_object_key)
        self._stub_unzipping_successful(aws_stubs=aws_stubs)

        response = handler(
            event=event, context=ctx.Context(), test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "unzipped": ['bank1/sample__ZP1.txt']
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_gracefully_handle_invalid_zip_files(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", bucket_name_incoming)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_zip_object_key)
        self._stub_unzipping_failure(aws_stubs=aws_stubs)

        response = handler(
            event=event, context=ctx.Context(), test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": "Unable to extract zip file."
            }
        }

        aws_stubs.s3.assert_no_pending_responses()

    @staticmethod
    def _assemble_key_for_incoming_bucket():
        return f"{created_csv_object_key.split('/')[0]}/{current_year}/{os.path.basename(created_csv_object_key)}"

    @staticmethod
    def _set_stubs_source_exists(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_response(
            method='copy_object',
            expected_params={
                'CopySource': {
                    "Bucket": bucket_name_upload, "Key": created_csv_object_key
                },
                'Bucket': bucket_name_incoming,
                'Key': Test_On_Upload_Handler._assemble_key_for_incoming_bucket()
            },
            service_response={}
        )

    @staticmethod
    def _set_stubs_copy_failures(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_client_error(
            method='copy_object',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )

    @staticmethod
    def _stub_unzipping_successful(aws_stubs: AwsStubs) -> None:
        zip_file_content = Fixtures.zipped_txt_file()
        aws_stubs.s3.add_response(
            method='get_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': created_zip_object_key
            },
            service_response={
                "Body": zip_file_content
            }
        )
        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': unzipped_object_key,
                'Body': ANY
            },
            service_response={}
        )

    @staticmethod
    def _stub_unzipping_failure(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_response(
            method='get_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': created_zip_object_key
            },
            service_response={
                "Body": BytesIO(b'not a zip file')
            }
        )


