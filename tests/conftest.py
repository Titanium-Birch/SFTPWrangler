# conftest.py serves as a means of providing fixtures to all tests in a directory
# see https://docs.pytest.org/en/7.1.x/reference/fixtures.html#conftest-py-sharing-fixtures-across-multiple-files
import tempfile
import boto3
import logging
import os
import paramiko
import pytest
import time
import timeit

from botocore.client import BaseClient
from botocore.config import Config
from botocore.stub import Stubber
from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin
from clients import get_secretsmanager_client, get_ssm_client, get_s3_client
from test_utils.entities.aws_stubs import AwsStubs
from typing import Iterator, Literal
from utils.sftp import convert_to_pkey, default_missing_host_key_policy

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

SFTP_TEST_USER = "sftpuser"  # this is the sftp user for atmoz/sftp container, see docker-compose.yml
REGION_WHEN_RUNNING_TESTS = "eu-west-1"  # this is the region for localstack container, see docker-compose.yml
BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS = "uploaded-files-during-test"  # this is the bucket name for localstack container, see docker-compose.yml
BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS = "incoming-files-during-test"  # this is the bucket name for localstack container, see docker-compose.yml
BUCKET_NAME_FILES_WHEN_RUNNING_TESTS = "attachment-files-during-test"  # this is the bucket name for localstack container, see docker-compose.yml
BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS = "categorized-files-during-test"  # this is the bucket name for localstack container, see docker-compose.yml
SSM_PARAMETER_NAME_BANK1 = "/aws/reference/secretsmanager/lambda/pull/bank1"
SSM_PARAMETER_NAME_PEER1 = "/aws/reference/secretsmanager/lambda/pull/peer1"
SSM_PARAMETER_NAME_PGP_BANK1 = "/aws/reference/secretsmanager/lambda/on_upload/pgp/bank1"
SSM_PARAMETER_NAME_WISE = "/aws/reference/secretsmanager/lambda/api/wise"
SSM_PARAMETER_NAME_ARCH = "/aws/reference/secretsmanager/lambda/rotate/marble.arch/arch/auth"


@dataclass
class ComposedEnvironment(DataClassJsonMixin):
    host_name: str
    localstack_port: int
    sftp_port: int

    def localstack_url(self) -> str:
        return f"http://{self.host_name}:{self.localstack_port}"


def create_aws_client(service_name: Literal["ssm"] | Literal["s3"] | Literal["secretsmanager"], endpoint_url: str) -> BaseClient:
    return boto3.client(service_name, aws_access_key_id="neededForAwsSDK", aws_secret_access_key="neededForAwsSDK",
                        endpoint_url=endpoint_url, config=Config(region_name=REGION_WHEN_RUNNING_TESTS))


def _is_responsive(host: str, sftp_port: int, localstack_port: int) -> bool:
    """When docker compose starts, we consider the system ready if the AWS SSM parameter
    containing the private key can be fetched and the key can be used to connect to the SFTP. 

    Args:
        host (str): host name under test
        sftp_port (int): port of the test SFTP server that docker compose starts
        localstack_port (int): port of the localstack that docker compose starts

    Returns:
        bool: _description_
    """
    try:
        localstack_url = "http://{}:{}".format(host, localstack_port)
        ssm_client = boto3.client("ssm", aws_access_key_id="neededForAwsSDK", aws_secret_access_key="neededForAwsSDK", endpoint_url=localstack_url, config=Config(region_name=REGION_WHEN_RUNNING_TESTS))

        # check if SSM parameters have been created yet
        ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_PEER1, WithDecryption=True)
        ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_PGP_BANK1, WithDecryption=True)
        ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_WISE, WithDecryption=True)
        ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_ARCH, WithDecryption=True)

        # check if this SSM parameter has been created and actually use is to connect to the SFTP
        bank1_parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key_bank1 = bank1_parameter.get("Parameter", {}).get("Value") or ""

        pk = convert_to_pkey(input=private_key_bank1)
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(default_missing_host_key_policy())
            ssh.connect(host, username="sftpuser", pkey=pk, port=sftp_port)
            return True
    except Exception as e:
        return False


class WaitTimeoutException(Exception):
    def __init__(self, container_logs, message="Timeout reached while waiting on service!"):
        self.container_logs = container_logs
        super().__init__(message)


def custom_wait(self, check, timeout, pause, clock=timeit.default_timer):
    """Wait until a service is responsive."""

    ref = clock()
    now = ref
    while (now - ref) < timeout:
        if check():
            return
        time.sleep(pause)
        now = clock()

    # get container logs to provide info about failure
    output = self._docker_compose.execute("logs").decode("utf-8")

    raise WaitTimeoutException(container_logs=output)

@pytest.fixture(scope='session')
def docker_compose_file(pytestconfig):
    return os.path.join(pytestconfig.rootdir, "docker-compose.yml")

@pytest.fixture(autouse=True)
def set_global_env_vars():
    """Set global environment variables that all tests need.
    """
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    yield


@pytest.fixture(scope="session")
def monkeysession(request):
    """By default, monkeypatch cannot be used in a session scoped fixture. Using monkeysession this will work.
    """
    mp = pytest.MonkeyPatch()
    request.addfinalizer(mp.undo)
    return mp


@pytest.fixture(scope="session")
def composed_environment(monkeysession, docker_ip, docker_services) -> ComposedEnvironment:
    """This fixture is used from tests that rely on services started via docker-compose. Before returning from this function,
    make sure all services are up and running.
    """
    from pytest_docker.plugin import Services
    # monkey patching library in order to see docker compose logs in case of an error, see https://github.com/avast/pytest-docker/issues/13#issuecomment-660186449
    monkeysession.setattr(Services, "wait_until_responsive", custom_wait)

    sftp_port = docker_services.port_for("sftp", 22)
    localstack_port = docker_services.port_for("localstack", 4566)
    environment_host = docker_ip

    try:
        # we are not returning until we can get a response from AWS SSM (localstack) and our custom SFTP server (atmoz/sftp)
        docker_services.wait_until_responsive(
            timeout=30.0,
            pause=0.5,
            check=lambda: _is_responsive(
                host=environment_host, sftp_port=sftp_port, localstack_port=localstack_port
            )
        )
    except WaitTimeoutException as e:
        logging.error(e.container_logs)
        raise e

    return ComposedEnvironment(host_name=environment_host, localstack_port=localstack_port, sftp_port=sftp_port)

@pytest.fixture
def aws_stubs() -> Iterator[AwsStubs]:
    ssm_stub = Stubber(get_ssm_client())
    s3_stub = Stubber(get_s3_client())
    secretsmanager_stub = Stubber(get_secretsmanager_client())
    with ssm_stub:
        with s3_stub:
                with secretsmanager_stub:
                    aws_stubs = AwsStubs()
                    aws_stubs.s3 = s3_stub
                    aws_stubs.ssm = ssm_stub
                    aws_stubs.secretsmanager = secretsmanager_stub
                    yield aws_stubs


@pytest.fixture
def set_gnupg_homedir():
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Setting GNUPGHOME to: {temp_dir}")
    os.environ["GNUPGHOME"] = temp_dir

    yield

