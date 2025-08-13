from io import BytesIO

import pytest
from aws_lambda_typing import context as ctx

from conftest import SSM_PARAMETER_NAME_BANK1, BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, SSM_PARAMETER_NAME_PEER1, \
    ComposedEnvironment, create_aws_client, SFTP_TEST_USER
from pull.app import ContextUnderTest, PullTestContext, handler
from pull.entities.sftp_pull_event import SftpPullEvent
from test_utils.fixtures import Fixtures
from test_utils.sftp_test_utils import upload_file_into_sftp
from utils.sftp import insert_timestamp
from utils.metrics import LocalMetricClient
from utils.s3 import list_bucket, upload_file
from utils.sftp import FingerprintIgnoringPolicy

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_Pull_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_pull_new_sftp_files_into_an_s3_bucket(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        peer_id = "bank1"
        sftp_host = composed_environment.host_name
        sftp_user = SFTP_TEST_USER
        sftp_port = composed_environment.sftp_port

        peer_config_json = Fixtures.peer_config(
            peer=peer_id, host_name=sftp_host, user_name=sftp_user, 
            port=sftp_port
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key
        
        new_file_path = "download/new_file.txt"
        remote_location = f"./{new_file_path}"
        new_file_content = BytesIO(b'Hello, World!')

        uploaded_file = upload_file_into_sftp(host_name=sftp_host, user_name=sftp_user, private_key=private_key, remote_location=remote_location, content=new_file_content, port=sftp_port)
        assert uploaded_file is not None
                
        pull_event = SftpPullEvent(id=peer_id)

        pull_test_context = PullTestContext(
            context_under_test=ContextUnderTest(
                ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(), current_datetime=lambda: current_datetime
            ), 
            fingerprint_verification_policy=FingerprintIgnoringPolicy()
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'imported': [new_file_path]
            }
        }

        bucket_items = list_bucket(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert f"{peer_id}/{new_file_path}" in object_keys

    @pytest.mark.integration
    def test_should_add_timestamps_to_downloaded_files_when_configured(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        peer_id = "bank1"
        sftp_host = composed_environment.host_name
        sftp_user = SFTP_TEST_USER
        sftp_port = composed_environment.sftp_port

        peer_config_json = Fixtures.peer_config(
            peer=peer_id, host_name=sftp_host, user_name=sftp_user, 
            port=sftp_port, timestamp_tagging=True
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key

        new_file_path = "download/filename.csv"
        remote_location = f"./{new_file_path}"
        new_file_content = BytesIO(b'name|age')

        uploaded_file = upload_file_into_sftp(host_name=sftp_host, user_name=sftp_user, private_key=private_key, remote_location=remote_location, content=new_file_content, port=sftp_port)
        assert uploaded_file is not None        
        
        pull_event = SftpPullEvent(id=peer_id)

        pull_test_context = PullTestContext(
            context_under_test=ContextUnderTest(
                ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(), current_datetime=lambda: current_datetime
            ),
            fingerprint_verification_policy=FingerprintIgnoringPolicy()
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'imported': [new_file_path]
            }
        }

        downloaded_file_s3_key = insert_timestamp(file_name=new_file_path, current_datetime=lambda: current_datetime, use_sgt=True)
        bucket_items = list_bucket(client=s3_client, prefix=peer_id, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert f"{peer_id}/{downloaded_file_s3_key}" in object_keys

    @pytest.mark.integration
    def test_should_find_previously_downloaded_files_only_for_the_current_peer(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        peer1 = "peer1"
        peer2 = "peer2"

        sftp_host = composed_environment.host_name
        sftp_user = SFTP_TEST_USER
        sftp_port = composed_environment.sftp_port      

        peer_config_json = Fixtures.peer_config(
            peer=peer1, host_name=sftp_host, user_name=sftp_user, 
            port=sftp_port, folder=f"./download/{peer1}"
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        new_file_name = "new_file.txt"
        new_file_path = f"download/{peer1}/{new_file_name}"

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        
        # create some test data for peer2
        upload_file(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS,
                    key=f"{peer2}/download/{new_file_name}", data=BytesIO(b'peer2 file'))
        
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_PEER1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        
        # upload a file of the same name into the SFTP
        uploaded_file = upload_file_into_sftp(host_name=sftp_host, user_name=sftp_user, private_key=private_key, remote_location=f"./{new_file_path}", content=BytesIO(b'peer1 file'), port=sftp_port)
        assert uploaded_file is not None        
        
        # pull peer1
        pull_event = SftpPullEvent(id=peer1)
        pull_test_context = PullTestContext(
            context_under_test=ContextUnderTest(
                ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(), current_datetime=lambda: current_datetime
            ), 
            fingerprint_verification_policy=FingerprintIgnoringPolicy()

        )
        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        
        # assert that the file was pulled even though a file of the same name existed for peer2
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'imported': [new_file_path]
            }
        }


    