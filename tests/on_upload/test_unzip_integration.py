import os

import pytest
from aws_lambda_typing import context as ctx
import urllib.parse

from conftest import BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client
from on_upload.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient, metric_lambda_on_upload_action, metric_lambda_on_upload_files_unzipped
from utils.s3 import list_bucket, upload_file

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_unzip_files_inside_the_upload_bucket(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)

        peer = "bank1"
        upload_object_key = f"{peer}/sample.zip"

        upload_file(
            client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, key=upload_object_key, data=Fixtures.sample_zip_content()
        )
        unzipped_object_key = f"{peer}/sample__U1234567_Activity_20230929.csv"

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
                'unzipped': [unzipped_object_key]
            }
        }

        bucket_items = list_bucket(client=s3_client, prefix=peer, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert unzipped_object_key in object_keys


    @pytest.mark.integration
    def test_should_unzip_files_containing_non_ascii_characters(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)

        peer = "bank1"
        zip_filename = "ZP1_(2023-11-18_12-22-17_SGT).zip"
        upload_object_key = f"{peer}/{zip_filename}"
        unzipped_object_key = f"{peer}/ZP1_(2023-11-18_12-22-17_SGT)__ZP1.txt"

        upload_file(
            client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, 
            key=upload_object_key, data=Fixtures.zipped_txt_file()
        )

        event = Fixtures.create_s3_event(
            bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=upload_object_key
        )

        local_metric_client = LocalMetricClient()
        test_context = ContextUnderTest(
            ssm_client=None, s3_client=s3_client, secretsmanager_client=None, metric_client=local_metric_client, current_datetime=lambda: current_datetime
        )
        response = handler(event=event, context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'unzipped': [unzipped_object_key]
            }
        }

        assert local_metric_client.rate_metrics[metric_lambda_on_upload_action] == [
            (1, {"peer": peer, "extension": ".zip"})
        ]
        assert local_metric_client.gauge_metrics[metric_lambda_on_upload_files_unzipped] == [
            (1, {"peer": peer})
        ]

        bucket_items = list_bucket(client=s3_client, prefix=peer, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert unzipped_object_key in object_keys

    @pytest.mark.integration 
    def test_should_safely_handle_malicious_zip_files(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        """Test that ZIP files with path traversal attempts are handled safely."""
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)

        peer = "bank1"
        upload_object_key = f"{peer}/malicious.zip"

        # Create a ZIP with malicious filenames
        malicious_zip = Fixtures.create_zip_with_files({
            "../../../etc/passwd": "sensitive content",
            "../../secret.txt": "another secret", 
            "/etc/hosts": "absolute path",
            "normal_file.txt": "normal content"
        })

        upload_file(
            client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, 
            key=upload_object_key, data=malicious_zip
        )

        event = Fixtures.create_s3_event(
            bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=upload_object_key
        )

        test_context = ContextUnderTest(
            ssm_client=None, s3_client=s3_client, secretsmanager_client=None, 
            metric_client=LocalMetricClient(), current_datetime=lambda: current_datetime
        )
        
        response = handler(event=event, context=ctx.Context(), test_context=test_context)
        
        # Should successfully process the ZIP but only extract safe files
        assert response["statusCode"] == 200
        unzipped_files = response["body"]["unzipped"]
        
        # Only the safe file should be extracted
        expected_safe_file = f"{peer}/malicious__normal_file.txt"
        assert expected_safe_file in unzipped_files
        assert len(unzipped_files) == 1  # Only one safe file extracted

        # Verify no malicious files were created
        bucket_items = list_bucket(client=s3_client, prefix=peer, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        
        # Should only contain the original ZIP and the one safe extracted file
        assert expected_safe_file in object_keys
        assert upload_object_key in object_keys
        
        # Should NOT contain any files that could be traversal attempts
        for key in object_keys:
            assert "etc" not in key  # No files containing etc
            assert ".." not in key   # No directory traversal sequences


    