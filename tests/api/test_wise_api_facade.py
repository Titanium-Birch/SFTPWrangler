from datetime import datetime
from botocore.stub import ANY
import pytest
from requests_mock import Mocker

from api.api_facade import WiseApiFacade
from api.utils.datetime_range_calculator import DatetimeRange, PreviousDayDatetimeRangeCalculator
from test_utils.entities.aws_stubs import AwsStubs
from utils.s3 import BucketItem

current_datetime = datetime.fromtimestamp(1697203293)
current_year = str(current_datetime.year)

class Test_Wise_Api_Facade:

    @pytest.mark.unit
    def test_should_fetch_previous_day_statements(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch: pytest.MonkeyPatch):
        peer_id = "the-peer"
        bucket_name = "upload"
        profile = 12345678
        sub_account = 98765432
        
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name)

        config = {"profile": profile, "sub_accounts": [sub_account]}

        url = f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
            f"?intervalStart=2023-10-12T00:00:00.000Z&intervalEnd=2023-10-12T23:59:59.999Z&type=COMPACT"
        
        requests_mock.get(
            url=url, 
            json=standard_account_statement_response
        )

        object_key = WiseApiFacade.assemble_object_key(
            peer_id=peer_id, profile=str(profile), sub_account=str(sub_account), type="balance_statement",
            range=DatetimeRange(start_time_iso="2023-10-12T00:00:00.000Z", end_time_iso="2023-10-12T23:59:59.999Z")
        )

        aws_stubs.s3.add_response(
            method='put_object',
            expected_params={
                'Bucket': bucket_name,
                'Key': object_key,
                'Body': ANY
            },
            service_response={}
        )

        facade = WiseApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, api_key="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == [BucketItem(key=object_key)]

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_not_upload_statements_without_transactions(self, requests_mock: Mocker, aws_stubs: AwsStubs, monkeypatch):
        peer_id = "the-peer"
        bucket_name = "upload"
        profile = 12345678
        sub_account = 98765432
        
        monkeypatch.setenv("BUCKET_NAME_UPLOAD", bucket_name)

        config = {"profile": profile, "sub_accounts": [sub_account]}

        url = f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
            f"?intervalStart=2023-10-12T00:00:00.000Z&intervalEnd=2023-10-12T23:59:59.999Z&type=COMPACT"
        
        no_transactions = dict(standard_account_statement_response)
        del no_transactions["transactions"]
        requests_mock.get(
            url=url, 
            json=no_transactions
        )

        facade = WiseApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, api_key="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime
            )
        )
        uploaded_items = facade.execute(config=config)
        assert uploaded_items == []

        aws_stubs.s3.assert_no_pending_responses()


    @pytest.mark.unit
    def test_should_handle_errors_fetching_balance_statements(self, requests_mock: Mocker, aws_stubs: AwsStubs):
        peer_id = "the-peer"
        profile = 12345678
        sub_account = 98765432        

        config = {"profile": profile, "sub_accounts": [sub_account]}

        url = f"{WiseApiFacade.WISE_BASE_URL_PROD}/profiles/{profile}/balance-statements/{sub_account}/statement.json" \
            f"?intervalStart=2023-10-12T00:00:00.000Z&intervalEnd=2023-10-12T23:59:59.999Z&type=COMPACT"
        
        requests_mock.get(url, status_code=403)

        facade = WiseApiFacade(
            s3_client=aws_stubs.s3.client, peer_id=peer_id, api_key="abc", 
            range_calculator=PreviousDayDatetimeRangeCalculator(
                current_datetime=lambda: current_datetime
            )
        )
        with pytest.raises(ValueError):
            facade.execute(config=config)

        aws_stubs.s3.assert_no_pending_responses()


standard_account_statement_response = {
    "accountHolder": {
        "type": "BUSINESS",
        "address": {
            "addressFirstLine": "Street 1234",
            "city": "City",
            "postCode": "Zip Code",
            "stateCode": None,
            "countryName": "Germany"
        },
        "businessName": "Business Name",
        "registrationNumber": "00000000000000000000",
        "companyType": "SOLE_TRADER"
    },
    "issuer": {
        "name": "Wise Europe SA",
        "firstLine": "Rue du Trône 100, 3rd floor",
        "city": "Brussels",
        "postCode": "1050",
        "stateCode": None,
        "countryCode": "bel",
        "country": "Belgium"
    },
    "bankDetails": [
        {
            "address": {
                "firstLine": "Wise",
                "secondLine": "Rue du Trône 100, 3rd floor",
                "postCode": "1050",
                "stateCode": None,
                "city": "Brussels",
                "country": "Belgium"
            },
            "accountNumbers": [
                {
                    "accountType": "IBAN",
                    "accountNumber": "BE00 0000 0000 0000"
                }
            ],
            "bankCodes": [
                {
                    "scheme": "Swift/BIC",
                    "value": "TRWIBEB1XXX"
                }
            ],
            "deprecated": False
        }
    ],
    "transactions": [
        {
            "type": "DEBIT",
            "date": "2023-10-12T08:42:56.560964Z",
            "amount": {
                "value": -13.67,
                "currency": "EUR",
                "zero": False
            },
            "totalFees": {
                "value": 0.28,
                "currency": "EUR",
                "zero": False
            },
            "details": {
                "type": "TRANSFER",
                "description": "Some description",
                "recipient": {
                    "name": "John Doe",
                    "bankAccount": "DE00000000000000000000"
                },
                "paymentReference": "",
                "creatorTrackingId": None
            },
            "exchangeDetails": None,
            "runningBalance": {
                "value": 0,
                "currency": "EUR",
                "zero": True
            },
            "referenceNumber": "TRANSFER-000000000",
            "attachment": None,
            "activityAssetAttributions": []
        }
    ],
    "startOfStatementBalance": {
        "value": 13.67,
        "currency": "EUR",
        "zero": False
    },
    "endOfStatementBalance": {
        "value": 0,
        "currency": "EUR",
        "zero": True
    },
    "endOfStatementUnrealisedGainLoss": None,
    "balanceAssetConfiguration": None,
    "query": {
        "intervalStart": "2023-10-12T00:00:00Z",
        "intervalEnd": "2023-10-12T23:59:59.999Z",
        "type": "COMPACT",
        "addStamp": False,
        "currency": "EUR",
        "profileId": 0,
        "timezone": "Z"
    },
    "request": {
        "id": "47be77a0-fcc9-4864-48db-0a9ea8839be4",
        "creationTime": "2023-10-13T10:19:48.927453259Z",
        "profileId": 0,
        "currency": "EUR",
        "balanceId": 0,
        "balanceName": None,
        "intervalStart": "2023-10-12T00:00:00Z",
        "intervalEnd": "2023-10-12T23:59:59.999Z"
    },
    "feeSummary": {
        "summaryTitle": "Fees Summary",
        "fromTitle": "From",
        "toTitle": "To",
        "feesTitle": "Fees",
        "feeSummaryItems": []
    },
    "locale": {
        "code": "en-GB"
    }
}
