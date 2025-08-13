from datetime import datetime
import os
from typing import Any, Dict, List, Tuple

import paramiko
import pytest
from aws_lambda_typing import context as ctx
from paramiko import AuthenticationException
from pytest_mock import MockerFixture
from pytest_mock.plugin import MockType
from requests_mock import Mocker

from pull.app import PullTestContext, handler
from pull.entities.sftp_pull_event import SftpPullEvent
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.common import peer_secret_id
from utils.metrics import LocalMetricClient, metric_lambda_pull
from utils.s3 import PAGINATOR_DEFAULT_PAGE_SIZE

peer_id = "bank1"
first_csv_file = "file1.csv"
second_csv_file = "file2.csv"
bucket_name_upload = "tb-terrasam-dev"


class Test_Pull_Handler:

    @pytest.mark.unit
    def test_should_fail_if_peer_config_cannot_be_fetched(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)
        
        appconfig_test_url = "http://localhost:2772/applications/foo/environments/bar/configurations/s3"
        monkeypatch.setenv("APP_CONFIG_PEERS_URL", appconfig_test_url)

        requests_mock.get(appconfig_test_url, status_code=400)

        pull_event = SftpPullEvent(id="random-bank")
        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context()            
        )
        
        response = handler(
            cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': "Unable to fetch peers config."
            }
        }

    @pytest.mark.unit
    def test_should_fail_when_pulling_unconfigured_peer(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)
        
        pull_event = SftpPullEvent(id=peer_id)
        peer_config_json = Fixtures.peer_config(peer="other_peer")
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context()            
        )
        
        response = handler(
            cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': f"Unable to find peer '{peer_id}' in configuration."
            }
        }

    @pytest.mark.unit
    def test_should_respond_with_error_if_secret_cannot_be_fetched(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)
        
        pull_event = SftpPullEvent(id=peer_id)
        peer_config_json = Fixtures.peer_config(peer=pull_event.id)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._setup_stubs_ssm_failure(aws_stubs=aws_stubs)

        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context()            
        )
        
        response = handler(
            cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': f"Unable to fetch parameter {peer_secret_id(peer_id=pull_event.id)} from "
                           f"AWS Secrets Manager."
            }
        }

    @pytest.mark.unit
    def test_should_respond_with_error_if_bucket_cannot_be_listed(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch, mocker: MockerFixture):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        pull_event = SftpPullEvent(id=peer_id)
        peer_config_json = Fixtures.peer_config(peer=pull_event.id)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._setup_stubs_s3_list_bucket_failure(aws_stubs=aws_stubs, event=pull_event)

        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context()            
        )
        
        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': "Unable to list existing items in AWS S3."
            }
        }

    @pytest.mark.unit
    def test_should_return_error_response_if_listing_sftp_fails(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch, mocker: MockerFixture):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        pull_event = SftpPullEvent(id=peer_id)
        peer_config_json = Fixtures.peer_config(peer=pull_event.id)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._setup_stubs_no_existing_files(aws_stubs=aws_stubs, event=pull_event)
        self._setup_mocks_sftp_connect_failure(mocker=mocker)
        
        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context()            
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                'message': "Something failed downloading new files in SFTP."
            }
        }

    @pytest.mark.unit
    def test_should_successfully_download_files(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch, mocker: MockerFixture):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name_upload)

        pull_event = SftpPullEvent(id=peer_id)
        peer_config_json = Fixtures.peer_config(peer=pull_event.id)
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._setup_stubs_no_existing_files(aws_stubs=aws_stubs, event=pull_event)
        download_mock = self._setup_sftp_mock(mocker=mocker)
        
        metric_client = LocalMetricClient()
        pull_test_context = PullTestContext(
            context_under_test=aws_stubs.test_context(metric_client=metric_client)           
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'imported': [first_csv_file, f"folder/{second_csv_file}"]
            }
        }

        assert metric_client.rate_metrics[metric_lambda_pull] == [
            (1, {"peer": pull_event.id})
        ]

        aws_stubs.ssm.assert_no_pending_responses()
        aws_stubs.s3.assert_no_pending_responses()

        download_mock.assert_called_once()


    @staticmethod
    def _setup_mocks_sftp_connect_failure(mocker: MockerFixture) -> MockType:
        def unauthenticated(*args, **kwargs):
            raise AuthenticationException()
        ssh_client_mock = mocker.patch.object(paramiko.SSHClient, 'connect')
        ssh_client_mock.side_effect = unauthenticated
        return ssh_client_mock

    def _setup_sftp_mock(self, mocker: MockerFixture) -> MockType:
        mock_response = [
            Fixtures.create_sftp_file_item(filename="file1.csv", location=f"./{first_csv_file}", size=100, last_modified=1633872000),
            Fixtures.create_sftp_file_item(filename="file2.csv", location=f"./folder/{second_csv_file}", size=100, last_modified=1633872000),
        ]
        return mocker.patch('pull.app._download_new_sftp_files', return_value=mock_response)

    def _setup_stubs_ssm_failure(self, aws_stubs: AwsStubs) -> None:
        self._setup_s3_stub(
            aws_stubs=aws_stubs, 
            list_object_contents=[]
        )
        
        aws_stubs.ssm.add_client_error(
            method='get_parameter',
            service_error_code='ParameterNotFound',
            service_message='The parameter couldnt be found. Verify the name and try again.',
            http_status_code=404,
        )

    def _setup_stubs_s3_list_bucket_failure(self, aws_stubs: AwsStubs, event: SftpPullEvent) -> None:
        self._setup_ssm_stub(aws_stubs=aws_stubs, event=event)
        
        aws_stubs.s3.add_client_error(
            method='list_objects_v2',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )

    def _setup_stubs_no_existing_files(self, aws_stubs: AwsStubs, event: SftpPullEvent) -> None:
        self._setup_ssm_stub(aws_stubs=aws_stubs, event=event)
        self._setup_s3_stub(
            aws_stubs=aws_stubs,
            list_object_contents=[]
        )

    def _setup_stubs_two_existing_files(self, aws_stubs: AwsStubs, event: SftpPullEvent) -> None:
        self._setup_ssm_stub(aws_stubs=aws_stubs, event=event)
        self._setup_s3_stub(
            aws_stubs=aws_stubs,
            list_object_contents=[
                {
                    "Key": f"{peer_id}/2023/{first_csv_file}",
                    "LastModified": datetime.fromisoformat("2021-11-30T12:58:14+00:00"),
                    "ETag": '"3a3c5ca43d2f01dba42314c1ca7e2237"',
                    "Size": 1417,
                    "StorageClass": "STANDARD",
                },
                {
                    "Key": f"{peer_id}/2023/{second_csv_file}",
                    "LastModified": datetime.fromisoformat("2021-11-30T12:58:05+00:00"),
                    "ETag": '"02bc99343bbdcbdefc9fe691b6f7deaa"',
                    "Size": 1332,
                    "StorageClass": "STANDARD",
                },
            ]
        )

    @staticmethod
    def _setup_s3_stub(aws_stubs: AwsStubs, list_object_contents: List[Dict[str, Any]]) -> None:
        if list_object_contents:    
            service_response = {
                "KeyCount": len(list_object_contents),
                "Contents": list_object_contents
            }
        else:
            # Contents is optional
            service_response = {
                "KeyCount": 0
            }

        aws_stubs.s3.add_response(
            method='list_objects_v2',
            expected_params={
                'Bucket': bucket_name_upload,
                'Prefix': peer_id,

                "MaxKeys": PAGINATOR_DEFAULT_PAGE_SIZE
            },
            service_response=service_response
        )

    @staticmethod
    def _setup_ssm_stub(aws_stubs: AwsStubs, event: SftpPullEvent) -> None:
        _, private_key = Fixtures.generate_rsa_keys()
        aws_stubs.ssm.add_response(
            method='get_parameter',
            expected_params={
                'Name': peer_secret_id(peer_id=event.id),
                'WithDecryption': True
            },
            service_response={
                'Parameter': {'Value': private_key.decode("UTF-8")}
            }
        )

