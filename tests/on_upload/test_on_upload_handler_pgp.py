import tempfile
from io import BytesIO
import os

import gnupg
import pytest
from aws_lambda_typing import context as ctx

from botocore.stub import ANY

from on_upload.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.crypt import pgp_private_key_secret_id

peer_id = "bank1"
created_gpg_object_key = f"{peer_id}/subfolder/ABC_123.csv.gpg"
decrypted_csv_object_key = ".".join(created_gpg_object_key.split(".")[:-1])
bucket_name_upload = "upload_bucket_name"


class Test_On_Upload_Handler_When_GPG_File_Is_Uploaded:

    @pytest.mark.unit
    def test_should_fail_when_files_needs_decryption_but_we_fail_to_fetch_private_key_secret(self, aws_stubs: AwsStubs):
        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_gpg_object_key)
        self._setup_ssm_failure(aws_stubs=aws_stubs)

        response = handler(event=event, context=ctx.Context(), test_context=aws_stubs.test_context())
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": "Unable to fetch parameter /aws/reference/secretsmanager/lambda/on_upload/pgp/bank1 "
                           "from AWS Secrets Manager."
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()

    @pytest.mark.unit
    def test_should_fail_when_files_needs_decryption_but_no_private_key_is_configured(self, aws_stubs: AwsStubs):
        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_gpg_object_key)
        self._setup_ssm(aws_stubs=aws_stubs, pgp_private_key="")

        response = handler(event=event, context=ctx.Context(), test_context=aws_stubs.test_context())
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": "You need to configure a PGP private key to process pgp decrypted files."
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    @pytest.mark.usefixtures("set_gnupg_homedir")
    def test_should_fail_if_file_cannot_be_decrypted(self, aws_stubs: AwsStubs):
        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_gpg_object_key)

        public_key, _, gpg = Fixtures.generate_gpg_keys(email="example@example.com")
        for key in gpg.list_keys(secret=True):  # generated keys are auto imported into the keyring, let's remove them
            gpg.delete_keys(key['fingerprint'], secret=True, expect_passphrase=False)
            gpg.delete_keys(key['fingerprint'])

        encrypted_data = self.encrypt_file(public_key=public_key, input_data=BytesIO(b'Foo Bar'))
        
        self._setup_s3(aws_stubs=aws_stubs, encrypted_data=BytesIO(str(encrypted_data).encode("UTF-8")))
        self._setup_ssm(aws_stubs=aws_stubs, pgp_private_key="broken private key")

        response = handler(event=event, context=ctx.Context(), test_context=aws_stubs.test_context())
        assert response == {
            "statusCode": 500,
            "headers": {},
            "body": {
                "message": "Unable to decrypt file: bank1/subfolder/ABC_123.csv.gpg using the configured PGP private.key: br**************ey"
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()



    @pytest.mark.unit
    @pytest.mark.usefixtures("set_gnupg_homedir")
    def test_should_successfully_decrypt_files(self, aws_stubs: AwsStubs):
        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_gpg_object_key)

        public_key, private_key, _ = Fixtures.generate_gpg_keys(email="example@example.com")

        encrypted_data = self.encrypt_file(public_key=public_key, input_data=BytesIO(b"Hello, World!"))
        
        self._setup_s3(aws_stubs=aws_stubs, encrypted_data=BytesIO(str(encrypted_data).encode("UTF-8")))
        self._setup_ssm(aws_stubs=aws_stubs, pgp_private_key=private_key.decode("utf-8"))

        response = handler(event=event, context=ctx.Context(), test_context=aws_stubs.test_context())
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "decrypted": [decrypted_csv_object_key]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @pytest.mark.unit
    @pytest.mark.usefixtures("set_gnupg_homedir")
    def test_should_decrypt_files_when_keyring_contains_multiple_keys_for_same_recipient(self, aws_stubs: AwsStubs):
        event = Fixtures.create_s3_event(bucket_name=bucket_name_upload, object_key=created_gpg_object_key)

        usr_public_key, usr_private_key, _ = Fixtures.generate_gpg_keys(email="example@example.com")
        encrypted_data = self.encrypt_file(public_key=usr_public_key, input_data=BytesIO(b"Foo Bar"))
        
        self._setup_s3(aws_stubs=aws_stubs, encrypted_data=BytesIO(str(encrypted_data).encode("UTF-8")))
        self._setup_ssm(aws_stubs=aws_stubs, pgp_private_key=usr_private_key.decode("utf-8"))

        peer_public_key, peer_private_key, _ = Fixtures.generate_gpg_keys(email="example@example.com")
        
        gnupghome = os.environ["GNUPGHOME"]
        gpg = gnupg.GPG(gnupghome=gnupghome)
        gpg.import_keys(peer_public_key)
        gpg.import_keys(peer_private_key)

        response = handler(event=event, context=ctx.Context(), test_context=aws_stubs.test_context())
        assert response == {
            "statusCode": 200,
            "headers": {},
            "body": {
                "decrypted": [decrypted_csv_object_key]
            }
        }

        aws_stubs.ssm.assert_no_pending_responses()


    @staticmethod
    def encrypt_file(public_key: bytes, input_data: BytesIO):
        gnupghome = os.environ["GNUPGHOME"]
        gpg = gnupg.GPG(gnupghome=gnupghome)
        gpg.import_keys(public_key)

        return gpg.encrypt_file(
            input_data,
            recipients="example@example.com",
            always_trust=True,
            armor=True,
        )

    @staticmethod
    def _setup_ssm_failure(aws_stubs: AwsStubs) -> None:
        aws_stubs.ssm.add_client_error(
            method='get_parameter',
            service_error_code='ParameterNotFound',
            service_message='The parameter could not be found. Verify the name and try again.',
            http_status_code=404,
        )

    @staticmethod
    def _setup_ssm(aws_stubs: AwsStubs, pgp_private_key: str) -> None:
        aws_stubs.ssm.add_response(
            method='get_parameter',
            expected_params={
                'Name': pgp_private_key_secret_id(peer_id=peer_id),
                'WithDecryption': True
            },
            service_response={
                'Parameter': {'Value': pgp_private_key}
            }
        )

    @staticmethod
    def _setup_s3(aws_stubs: AwsStubs, encrypted_data: BytesIO) -> None:
        aws_stubs.s3.add_response(
            method='get_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': created_gpg_object_key
            },
            service_response={
                "Body": encrypted_data
            }
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name_upload,
                'Key': decrypted_csv_object_key,
                'Body': ANY
            },
            service_response={}
        )

