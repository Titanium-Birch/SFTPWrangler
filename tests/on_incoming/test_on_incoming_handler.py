import os
from typing import List

import pytest
from aws_lambda_typing import context as ctx
from botocore.stub import ANY
from requests_mock import Mocker

from on_incoming.app import handler
from test_utils.entities.aws_stubs import AwsStubs
from test_utils.fixtures import Fixtures
from utils.metrics import LocalMetricClient

peer = "bank1"
another_peer = "bank2"
incoming_csv_object_key = f"{peer}/2023/Deposit and ST_Report_20230927_110018.csv"
bucket_name_incoming = "incoming_bucket_name"
bucket_name_categorized = "categorized_bucket_name"
category1_id = "deposit_and_st_report"
category2_id = "fixed_income_report"
current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)


class Test_On_Incoming_Handler:

    @pytest.mark.unit
    def test_should_categorize_incoming_files_for_peer_when_configured(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)

        peer_config_json = Fixtures.peer_config(
            peer=peer, 
            categories=[
                {"category_id": category1_id, "filename_patterns": ["Deposit and ST_Report_\\d{8}_\\d{6}.csv"]},
                {"category_id": category2_id, "filename_patterns": ["Fixed_Income_Report_\\d{8}_\\d{6}.csv", "Fixed Income Report_\\d{8}_\\d{6}.csv"]}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_incoming, object_key=incoming_csv_object_key)
        self._set_stubs_success(aws_stubs=aws_stubs, categories_found=[category1_id])

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(current_datetime=current_datetime, metric_client=metric_client)
        )
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                "categorized": [{"file_name": os.path.basename(incoming_csv_object_key), "category_id": category1_id, 
                                 "peer": peer, "transformations_applied": []}]
            }
        }
        aws_stubs.s3.assert_no_pending_responses()



    @pytest.mark.unit
    def test_should_handle_appconfig_failures_gracefully(self, aws_stubs: AwsStubs, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)

        appconfig_test_url = "http://localhost:2772/applications/foo/environments/bar/configurations/s3"
        monkeypatch.setenv("APP_CONFIG_PEERS_URL", appconfig_test_url)

        requests_mock.get(appconfig_test_url, status_code=404)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_incoming, object_key=incoming_csv_object_key)

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(current_datetime=current_datetime, metric_client=metric_client)
        )
        assert response == {
            "statusCode": 500, 
            "headers": {},
            "body": {
                "message": "Unable to fetch peers config."
            }
        }
        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_support_categorizing_the_same_file_multiple_times_when_configured(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)

        peer_config_json = Fixtures.peer_config(
            peer=peer, 
            categories=[
                {"category_id": category1_id, "filename_patterns": ["Deposit and ST_Report_\\d{8}_\\d{6}.csv"]},
                {"category_id": category2_id, "filename_patterns": ["Fixed_Income_Report_\\d{8}_\\d{6}.csv", "Deposit and ST_Report_.*"]}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        event = Fixtures.create_s3_event(bucket_name=bucket_name_incoming, object_key=incoming_csv_object_key)
        self._set_stubs_success(aws_stubs=aws_stubs, categories_found=[category1_id, category2_id])

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(current_datetime=current_datetime, metric_client=metric_client)
        )
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                "categorized": [
                    {"file_name": os.path.basename(incoming_csv_object_key), "category_id": category1_id, "peer": peer,
                     "transformations_applied": []},
                    {"file_name": os.path.basename(incoming_csv_object_key), "category_id": category2_id, "peer": peer,
                     "transformations_applied": []}
                ]
            }
        }
        aws_stubs.s3.assert_no_pending_responses()



    @pytest.mark.unit
    def test_should_apply_configurations_per_peer(self, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_CATEGORIZED", bucket_name_categorized)

        peer_config_json = Fixtures.peer_config(
            peer=another_peer, 
            categories=[
                {"category_id": category1_id, "filename_patterns": ["Deposit and ST_Report_\\d{8}_\\d{6}.csv"]}
            ]
        )
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        self._set_stubs_success(aws_stubs=aws_stubs, categories_found=[])

        event = Fixtures.create_s3_event(bucket_name=bucket_name_incoming, object_key=incoming_csv_object_key)

        metric_client = LocalMetricClient()
        response = handler(
            event=event, 
            context=ctx.Context(), 
            test_context=aws_stubs.test_context(current_datetime=current_datetime, metric_client=metric_client)
        )
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                "categorized": []
            }
        }


    @staticmethod
    def _assemble_key_for_categorized_bucket(category_name: str):
        return f"{incoming_csv_object_key.split('/')[0]}/{category_name}/{current_year}/{os.path.basename(incoming_csv_object_key)}"

    @staticmethod
    def _set_stubs_success(aws_stubs: AwsStubs, categories_found: List[str],
                           transformations: List[str] = []) -> None:
        for category_found in categories_found:
            # depending on whether we apply transformations, expect either a copy or a get+put
            if transformations and len(transformations) > 0:
                aws_stubs.s3.add_response(
                    method='get_object',
                    service_response={
                        'Body': 'funny-csv-contents'
                    }
                ) # TODO: return the funny-csv file contents here
                aws_stubs.s3.add_response(
                    method='put_object',
                    expected_params={
                        'Bucket': bucket_name_categorized,
                        'Key': Test_On_Incoming_Handler._assemble_key_for_categorized_bucket(category_name=category_found)
                    },
                    service_response={}
                )
            else:
                aws_stubs.s3.add_response(
                    method='copy_object',
                    expected_params={
                        'CopySource': {
                            "Bucket": bucket_name_incoming, "Key": incoming_csv_object_key
                        },
                        'Bucket': bucket_name_categorized,
                        'Key': Test_On_Incoming_Handler._assemble_key_for_categorized_bucket(category_name=category_found)
                    },
                    service_response={}
                )

    @staticmethod
    def _set_stubs_copy_failures(aws_stubs: AwsStubs) -> None:
        aws_stubs.s3.add_client_error(
            method='copy_object',
            service_error_code='NoSuchBucket',
            service_message='The specified bucket does not exist.',
            http_status_code=404
        )



