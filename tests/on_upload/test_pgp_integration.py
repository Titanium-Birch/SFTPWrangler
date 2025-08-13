import csv
from io import BytesIO, StringIO
import io
import os
from typing import List, Tuple
from botocore.client import BaseClient
import gnupg
import pytest

from aws_lambda_typing import context as ctx
from conftest import BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS, BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client
from on_upload.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient
from utils.s3 import get_object, list_bucket, upload_file

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Upload_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    @pytest.mark.usefixtures("set_gnupg_homedir")
    def test_should_successfully_decrypt_files_having_a_gpg_extension(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        localstack_url = composed_environment.localstack_url()
        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)

        peer = "bank1"
        upload_object_key = f"{peer}/subfolder1/folder2/ABC_123.csv.gpg"

        # prepare & encrypt sample csv and upload into S3. Secrets Manager will hold the matching private key
        prepared_csv_data = self.prepare_encrypted_csv(s3_client=s3_client, object_key=upload_object_key)   

        decrypted_object_key = ".".join(upload_object_key.split(".")[:-1])
        event = Fixtures.create_s3_event(
            bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=upload_object_key
        )

        test_context = ContextUnderTest(
            ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )

        # trigger the handler so it will decrypt the file
        response = handler(event=event, context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'decrypted': [decrypted_object_key]
            }
        }

        # make sure object name in S3 and contents are properly decrypted
        loaded = get_object(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, object_key=decrypted_object_key)
        loaded_data = StringIO(loaded.read().decode("UTF-8"))
        loaded_csv_data = [row for row in csv.reader(loaded_data, delimiter=";", lineterminator="\n")]

        assert loaded_csv_data == prepared_csv_data


    def prepare_encrypted_csv(self, s3_client: BaseClient, object_key: str) -> List[List[str]]:
        data = [
            ['Name', 'Age', 'City'],
            ['John', '25', 'New York'],
            ['Alice', '30', 'London']
        ]
        csv_data: StringIO = Fixtures.sample_csv_data(data=data)        
        csv_data_bytes = BytesIO(csv_data.getvalue().encode("UTF-8"))

        public_key, _, _ = Fixtures.generate_gpg_keys(email="example@example.com")
        encrypted_csv_data = self.encrypt_file(public_key=public_key, input_data=csv_data_bytes)
        upload_file(client=s3_client, bucket_name=BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, key=object_key, 
                    data=encrypted_csv_data.data) 
        return data


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