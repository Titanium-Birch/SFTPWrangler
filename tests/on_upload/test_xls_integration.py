import pandas as pd
import pytest

from aws_lambda_typing import context as ctx
from conftest import BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client
from io import BytesIO
from on_upload.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient
from utils.s3 import get_object, list_bucket, upload_file

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_convert_xls_files(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)

        peer = "bank1"
        upload_object_key = f"{peer}/single_sheet.xls"

        upload_file(
            client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, key=upload_object_key, 
            data=Fixtures.sample_excel_content(filename="single_sheet.xls")
        )
        converted_object_key = f"{peer}/single_sheet_sheet0_Sheet1.csv"

        event = Fixtures.create_s3_event(
            bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=upload_object_key
        )

        test_context = ContextUnderTest(
            ssm_client=None, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )
        response = handler(event=event, context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'converted': [converted_object_key]
            }
        }

        bucket_items = list_bucket(client=s3_client, prefix=peer, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert converted_object_key in object_keys

        csv_stream = get_object(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=converted_object_key)
        df = pd.read_csv(BytesIO(csv_stream.read()))
        assert len(df) == 1
        assert "John" == df.loc[0, 'Name']