from io import BytesIO

from datetime import datetime
import logging
import typing

import pytest

from conftest import SSM_PARAMETER_NAME_BANK1, ComposedEnvironment, create_aws_client, SFTP_TEST_USER
from test_utils.sftp_test_utils import upload_file_into_sftp
from utils.sftp import SftpFileItem, download_new_files

logger = logging.getLogger()
logger.setLevel(logging.INFO)


current_datetime = datetime.fromtimestamp(1697203293)
current_year = str(current_datetime.year)

class Test_Paramiko_Library:

    @pytest.mark.integration
    def test_should_successfully_download_files(self, composed_environment: ComposedEnvironment):
        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key

        sftp_host = composed_environment.host_name
        sftp_user = SFTP_TEST_USER
        sftp_port = composed_environment.sftp_port
        
        new_file_name = "uploaded.txt"
        new_file_location = f"./download/{new_file_name}"
        new_file_content = BytesIO(b'Testing')

        uploaded_file = upload_file_into_sftp(host_name=sftp_host, user_name=sftp_user, private_key=private_key, remote_location=new_file_location, content=new_file_content, port=sftp_port)
        assert uploaded_file is not None

        def log(sftp_file_item: SftpFileItem, file_content: typing.BinaryIO) -> None:
            file_content.seek(0)
            if sftp_file_item.filename == new_file_name:
                assert file_content.read().decode('utf-8') == "Testing"
        
        successfully_downloaded = download_new_files(
            sftp_user=sftp_user,
            sftp_host=sftp_host,
            sftp_port=sftp_port,
            ssh_private_key=private_key,
            remote_folder=None,
            download_eligable=lambda sftp_item: True,
            download_handler=log,
            missing_host_key_policy=None,
        )

        assert len([item for item in successfully_downloaded if item.filename == new_file_name]) == 1


    @pytest.mark.integration
    def test_should_download_files_under_the_specified_folder(self, composed_environment: ComposedEnvironment):
        localstack_url = composed_environment.localstack_url()
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        
        parameter = ssm_client.get_parameter(Name=SSM_PARAMETER_NAME_BANK1, WithDecryption=True)
        private_key = parameter.get("Parameter", {}).get("Value")
        assert private_key

        sftp_host = composed_environment.host_name
        sftp_user = SFTP_TEST_USER
        sftp_port = composed_environment.sftp_port
        
        new_sftp_file_location = f"./download/randomBank/1.txt"

        uploaded = upload_file_into_sftp(host_name=sftp_host, user_name=sftp_user, private_key=private_key, remote_location=new_sftp_file_location, content=BytesIO(b'randomBank file content'), port=sftp_port)
        
        def log(sftp_file_item: SftpFileItem, file_content: typing.BinaryIO) -> None:
            file_content.seek(0)
            assert file_content.read().decode('utf-8') == "randomBank file content"
        
        successfully_downloaded = download_new_files(
            sftp_user=sftp_user,
            sftp_host=sftp_host,
            sftp_port=sftp_port,
            ssh_private_key=private_key,
            remote_folder="./download/randomBank",
            download_eligable=lambda sftp_item: True,
            download_handler=log,
            missing_host_key_policy=None,
        )

        assert len(successfully_downloaded) == 1
        assert successfully_downloaded[0].location == uploaded.location
    