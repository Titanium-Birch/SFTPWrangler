import io
import os
import pandas as pd
import pytest

from aws_lambda_typing import context as ctx
from botocore.stub import ANY

from on_upload.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient, metric_lambda_on_upload

created_xls_object_key = "bank1/single_sheet.xls"
created_xlsx_object_key = "bank1/two_sheets.xlsx"

bucket_name_upload = "upload_bucket_name"
current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler_When_Called_With_Excel_Files:

    @pytest.mark.unit
    def test_should_convert_xls_files_having_one_sheet_into_a_single_csv_file(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        self._stub_conversion_single(aws_stubs=aws_stubs)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_xls_object_key)

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
                "converted": ["bank1/single_sheet_sheet0_Sheet1.csv"]
            }  
        }

        assert metric_client.rate_metrics[metric_lambda_on_upload] == [
            (1, {"peer": created_xls_object_key.split("/")[0]})
        ]

        aws_stubs.s3.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_convert_xlsx_files_having_two_sheets_into_two_csv_files(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        self._stub_conversion_multiple(aws_stubs=aws_stubs)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_xlsx_object_key)

        response = handler(
            event=event, context=ctx.Context(), test_context=aws_stubs.test_context(current_datetime=current_datetime)
        )
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                "converted": ['bank1/two_sheets_sheet0_Names.csv', 'bank1/two_sheets_sheet1_Popular First Names.csv']
            }   
        }

        aws_stubs.s3.assert_no_pending_responses()


    @staticmethod
    def _stub_conversion_single(aws_stubs: AwsStubs) -> None:
        excel_file_content = Fixtures.sample_excel_content(filename="single_sheet.xls")
        aws_stubs.s3.add_response(
            method='get_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': created_xls_object_key
            },
            service_response={
                "Body": excel_file_content
            }
        )

        base_path, _ = os.path.splitext(created_xls_object_key)

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': f"{base_path}_sheet0_Sheet1.csv",
                'Body': ANY
            },
            service_response={}
        )


    @staticmethod
    def _stub_conversion_multiple(aws_stubs: AwsStubs) -> None:
        excel_file_content = Fixtures.sample_excel_content(filename="two_sheets.xlsx")
        aws_stubs.s3.add_response(
            method='get_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': created_xlsx_object_key
            },
            service_response={
                "Body": excel_file_content
            }
        )

        base_path, _ = os.path.splitext(created_xlsx_object_key)

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': f"{base_path}_sheet0_Names.csv",
                'Body': ANY
            },
            service_response={}
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': f"{base_path}_sheet1_Popular First Names.csv",
                'Body': ANY
            },
            service_response={}
        )
