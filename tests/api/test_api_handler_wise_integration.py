import pytest
from requests_mock import Mocker
from api.api_facade import WiseApiFacade
from api.entities.invoke_api_event import InvokeApiEvent
from utils.common import peer_secret_id
from utils.metrics import LocalMetricClient
from utils.s3 import list_bucket, upload_file
from conftest import BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS, ComposedEnvironment, \
    create_aws_client
from api.app import ContextUnderTest, handler
from test_utils.fixtures import Fixtures
from aws_lambda_typing import context as ctx

current_datetime = Fixtures.fixed_datetime()
current_year = str(current_datetime.year)

class Test_Api_Handler_When_Running_Against_Containers:

    @pytest.mark.integration
    def test_should_successfully_download_statements_from_wise(self, composed_environment: ComposedEnvironment, requests_mock: Mocker, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", BUCKET_NAME_UPLOAD_WHEN_RUNNING_TESTS)

        peer = "wise"
        profile = 89898989
        sub_account = 56565656

        localstack_url = composed_environment.localstack_url()        
        
        config = {"profile": profile, "sub_accounts": [sub_account]}
        peer_config_json = Fixtures.api_peer_config(peer = peer, api_config = {"wise": config})
        monkeypatch.setenv("PEERS_JSON_UNDER_TEST", peer_config_json)

        url = f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
            f"?intervalStart=2023-10-12T00:00:00.000Z&intervalEnd=2023-10-12T23:59:59.999Z&type=COMPACT"

        requests_mock.get(url=url, json=dummy_account_statement_response)

        s3_client = create_aws_client(service_name="s3", endpoint_url=localstack_url)
        ssm_client = create_aws_client(service_name="ssm", endpoint_url=localstack_url)
        
        test_context = ContextUnderTest(
            ssm_client=ssm_client, s3_client=s3_client, secretsmanager_client=None, metric_client=LocalMetricClient(),
            current_datetime=lambda: current_datetime
        )
        response = handler(cloudwatch_event=InvokeApiEvent(id=peer).to_dict(), context=ctx.Context(), test_context=test_context)
        assert response == {
            "statusCode": 200, 
            "headers": {},
            "body": {
                'fetched': ['wise/89898989/56565656_balance_statement_2023-10-12T00:00:00.000Z_2023-10-12T23:59:59.999Z.json']
            }
        }


dummy_account_statement_response = {
    "accountHolder": {
        "type": "BUSINESS",
    },
    "issuer": {
        "name": "Wise Europe SA",
    },
    "bankDetails": [
    ],
    "transactions": [
        {
            "type": "DEBIT"
        }
    ],
}
