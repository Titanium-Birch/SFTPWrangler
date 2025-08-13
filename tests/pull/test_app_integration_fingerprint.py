from typing import List
from paramiko import PKey
import pytest
from aws_lambda_typing import context as ctx

from conftest import SSM_PARAMETER_NAME_BANK1, BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client, SFTP_TEST_USER
from pull.app import ContextUnderTest, PullTestContext, handler
from pull.entities.sftp_pull_event import SftpPullEvent
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient
from utils.sftp import FingerprintEnforcingPolicy

peer_id = "bank1"
current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class FingerprintEnforcingPolicyUnderTest(FingerprintEnforcingPolicy):
    def __init__(self: "FingerprintEnforcingPolicyUnderTest", fingerprint_under_test: str, peer: str, fingerprints: List[str]) -> None:
        super().__init__(peer_id=peer, allowed_fingerprints=fingerprints or [])
        self.fingerprint_under_test = fingerprint_under_test

    def _sha256_fingerprint(self: "FingerprintEnforcingPolicyUnderTest", key: PKey) -> str:
        return self.fingerprint_under_test


class Test_Pull_Handler_During_Integration:

    @pytest.mark.integration
    def test_should_connect_to_servers_that_have_their_fingerprints_configured(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)
        
        sha256_fingerprint = "SHA256:O/8NE58NE58NE58NE58NE58NE58NE58NE58NE58NE5"
        peer_config_json = Fixtures.peer_config(
            peer=peer_id, host_name=composed_environment.host_name, 
            user_name=SFTP_TEST_USER, port=composed_environment.sftp_port,
            fingerprints=[sha256_fingerprint]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key
      
        pull_event = SftpPullEvent(id=peer_id)

        policy_under_test = FingerprintEnforcingPolicyUnderTest(fingerprint_under_test=sha256_fingerprint, peer=peer_id, fingerprints=[sha256_fingerprint])
        pull_test_context = PullTestContext(
            context_under_test=ContextUnderTest(
                ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient()
            ),
            fingerprint_verification_policy=policy_under_test
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response["statusCode"] == 200


    @pytest.mark.integration
    def test_should_not_connect_to_a_peers_server_if_no_fingerprints_are_configured(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        peer_config_json = Fixtures.peer_config(
            peer=peer_id, host_name=composed_environment.host_name, 
            user_name=SFTP_TEST_USER, port=composed_environment.sftp_port
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key
      
        sha256_fingerprint = "SHA256:O/8NE58NE58NE58NE58NE58NE58NE58NE58NE58NE5"
        pull_event = SftpPullEvent(id=peer_id)

        policy_under_test = FingerprintEnforcingPolicyUnderTest(fingerprint_under_test=sha256_fingerprint, peer=peer_id, fingerprints=list())
        pull_test_context = PullTestContext(
            context_under_test=ContextUnderTest(
                ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient()
            ),
            fingerprint_verification_policy=policy_under_test
        )

        response = handler(cloudwatch_event=pull_event.to_dict(), context=ctx.Context(), pull_test_context=pull_test_context)
        assert response["statusCode"] == 500

