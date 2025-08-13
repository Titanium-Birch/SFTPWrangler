import os
from typing import Any, Dict
import pytest
from utils.metrics import LocalMetricClient
from utils.s3 import get_object, list_bucket, upload_file
from conftest import BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client, BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS
from on_incoming.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from io import BytesIO
from aws_lambda_typing import context as ctx

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)

class Test_On_Incoming_Handler_When_Running_Against_Containers:

    @pytest.fixture(autouse=True)
    def setup(self, composed_environment: ComposedEnvironment, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_INCOMING", BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS)
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS)

        localstack_url      = composed_environment.localstack_url()
        self.s3_client      = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        self.peer           = "sample-bank"
        peer_config_json    = Fixtures.peer_config(
            peer=self.peer, 
            categories=[
                {"category_id": "with_transformation", "filename_patterns": ["^.*file1\\.csv$"], "transformations":["RemoveNewlinesInCsvFieldsTransformer"]},
                {"category_id": "without_transformation", "filename_patterns": ["^.*file2\\.csv$"], "transformations":[]}
            ]
        )

        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self.test_context = ContextUnderTest(
            ssm_client=None, s3_client=self.s3_client, secretsmanager_client=None,
            metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )


    # context: 
    #   - the incoming file matches a category-pattern
    # sub-context: 
    #   - category config specifies a transformation (see localstack-script.sh)
    # expected: 
    #   - a transformed file is delivered into the categorized bucket
    @pytest.mark.integration
    def test_should_match_incoming_file_against_category_with_transformations(self):
        expected_category_match = "with_transformation"
        file_name = "file1.csv"

        test_files_path = os.path.join(os.path.dirname(__file__), '..', 'files', 'transformer')
        with open(os.path.join(test_files_path, 'funny-csv-with-toprows.csv'), "r") as file:
            file_contents = file.read()

        self._upload_file_to_incoming(file_name=file_name, file_content=BytesIO(file_contents.encode('utf-8')))

        response = self._run_incoming_handler()
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'categorized': [
                    {
                        'file_name': file_name, 
                        'category_id': expected_category_match, 
                        'peer': self.peer, 
                        'transformations_applied': ["RemoveNewlinesInCsvFieldsTransformer"]
                    }
                ]
            }
        }

        expected_object_key = f"{self.peer}/{expected_category_match}/folder/{file_name}"

        with open(
            os.path.join(test_files_path,
                         'funny-csv-with-toprows.csv'), "r") as file:
            expected_content = file.read()

        self._assert_item_in_categorized_bucket(object_key=expected_object_key, expected_content=expected_content)


    # context: 
    #   - the incoming file matches a category-pattern
    # sub-context: 
    #   - the category is not configured with any transformation (see localstack-script.sh)
    # expected: 
    #   - a original file is delivered into the categorized bucket
    @pytest.mark.integration
    def test_should_match_an_incoming_file_against_category_without_transformations(self):
        expected_category_match = "without_transformation"
        file_name = "file2.csv"
        file_content = "Foo|Bar"

        self._upload_file_to_incoming(file_name=file_name, file_content=BytesIO(file_content.encode("utf-8")))

        response = self._run_incoming_handler()
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'categorized': [
                    {
                        'file_name': file_name, 
                        'category_id': expected_category_match, 
                        'peer': self.peer, 
                        'transformations_applied': []
                    }
                ]
            }
        }

        expected_object_key = f"{self.peer}/{expected_category_match}/folder/{file_name}"
        self._assert_item_in_categorized_bucket(object_key=expected_object_key, expected_content=file_content)


    def _assert_bucket_empty(self) -> None:
        bucket_items = list_bucket(client      = self.s3_client,
                                   prefix      = self.peer, 
                                   bucket_name = BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS)
        assert len(bucket_items) == 0

    def _upload_file_to_incoming(self, file_name: str, file_content: BytesIO) -> None:
        upload_object_key   = f"{self.peer}/folder/{file_name}"
        upload_file(client=self.s3_client, bucket_name=BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS,
                    key=upload_object_key, data=file_content)
        self.event = Fixtures.create_s3_event(bucket_name=BUCKET_NAME_INCOMING_WHEN_RUNNING_TESTS,
                                         object_key=upload_object_key, event_time=current_datetime.isoformat())

    def _run_incoming_handler(self) -> Dict[str, Any]:
        return handler(event=self.event, context=ctx.Context(), test_context=self.test_context)

    def _assert_item_in_categorized_bucket(self, object_key: str, expected_content: str) -> None:
        # assert categorisation
        bucket_items = list_bucket(client = self.s3_client,
                                   prefix = self.peer, 
                                   bucket_name = BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS)
        object_keys = {f.key for f in bucket_items}
        assert object_key in object_keys

        # assert transformation
        transformed_item_content_bin = get_object(client=self.s3_client, bucket_name=BUCKET_NAME_CATEGORIZED_WHEN_RUNNING_TESTS, object_key=object_key)
        transformed_item_content = transformed_item_content_bin.read().decode("UTF-8")
        assert transformed_item_content == expected_content


