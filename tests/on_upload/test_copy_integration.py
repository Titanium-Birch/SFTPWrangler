from io import BytesIO

import pytest
from aws_lambda_typing import context as ctx

from conftest import BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client, BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS
from on_upload.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient
from utils.s3 import list_bucket, upload_file

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_copy_files_into_the_incoming_bucket(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS)
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)

        peer = "bank1"
        file_name = "test_data.csv"
        upload_object_key = f"{peer}/folder/{file_name}"
        incoming_object_key = f"{peer}/{current_year}/{file_name}"

        upload_file(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS,
                    key=upload_object_key, data=BytesIO(b'id|name|data'))

        event = Fixtures.create_s3_event(bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS,
                                         object_key=upload_object_key, event_time=current_datetime.isoformat())

        test_context = ContextUnderTest(
            ssm_client=None, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )
        response = handler(event=event, context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'copied': [incoming_object_key]
            }
        }

        bucket_items = list_bucket(client=s3_client, prefix=peer, bucket_name=BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert incoming_object_key in object_keys


    