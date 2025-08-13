import csv
import gnupg
import io
import json
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Any, Dict, List, Literal, Optional, Tuple

from aws_lambda_typing.events import APIGatewayProxyEventV2, S3Event

from api.entities.wise_event import WiseEvent, WiseEventData, WiseEventDataResource
from utils.sftp import SftpFileItem


class Fixtures:
    @staticmethod
    def fixed_datetime() -> datetime:
        return datetime.fromtimestamp(1697203293, timezone.utc)
    
    @staticmethod
    def create_sftp_file_item(filename: str, location: str, size: Optional[int] = None, last_modified: Optional[int] = None) -> SftpFileItem:
        return SftpFileItem(filename=filename, location=location, size=size, last_modified=last_modified)
    
    @staticmethod
    def create_s3_event(bucket_name: str, object_key: str, event_time: Optional[str] = None) -> S3Event:
        if not event_time:
            event_time = datetime.now().isoformat()

        record = {
            "s3": {
                "s3SchemaVersion": "notUsed",
                "configurationId": "notUsed",
                "bucket": {
                    "name": bucket_name,
                    "ownerIdentity": {
                        "principalId": "notUsed"
                    },
                    "arn": "notUsed"
                },
                "object": {
                    "key": object_key
                }
            },
            "eventTime": event_time
        }        
        return {"Records": [record]} # type: ignore
    

    @staticmethod
    def create_api_gateway_event(body: Optional[str], headers: Optional[Dict[str, str]] = None) -> APIGatewayProxyEventV2:
        event = {
            "version": "version",
            "routeKey": "routeKey",
            "rawPath": "rawPath",
            "rawQueryString": "rawQueryString",
            "cookies": None,
            "headers": headers or {},
            "queryStringParameters": dict(),
            "requestContext": {},
            "pathParameters": dict(),
            "isBase64Encoded": False,
            "stageVariables": dict()
        }

        if body is not None:
            event["body"] = body

        return event # type: ignore
        

    @staticmethod
    def create_wise_event(event_type: str = "balances#update", profile_id: int = 1) -> WiseEvent:
        return WiseEvent(
            subscription_id="subscription_id",
            event_type=event_type,
            schema_version="schema_version",
            sent_at="sent_at",
            data=WiseEventData(
                resource=WiseEventDataResource(
                    id=1,
                    profile_id=profile_id,
                    type="type"
                )
            )
        )
    

    @staticmethod
    def sample_zip_content() -> BytesIO:
        csv_content = """H,U1234567,Activity,20231002,02:00:56,20230929,1.991,
Type,AccountID,ConID,SecurityID,Symbol,BBTicker,BBGlobalID,SecurityDescription,AssetType,Currency,BaseCurrency,TradeDate,TradeTime,SettleDate,OrderTime,TransactionType,Quantity,UnitPrice,GrossAmount,SECFee,Commission,Tax,Net,NetInBase,TradeID,TaxBasisElection,Description,FxRateToBase,ContraPartyName,ClrFirmID,Exchange,MasterAccountID,Van,AwayBrokerCommission,OrderID,ClientReference,TransactionID,ExecutionID,CostBasis,Flag,
T,3,"""
        return Fixtures.create_zip_with_files({"U1234567_Activity_20230929.csv": csv_content})
    
    @staticmethod
    def zipped_txt_file() -> BytesIO:
        """Creates a ZIP file in memory containing a single text file with content 'it works'"""
        return Fixtures.create_zip_with_files({"ZP1.txt": "it works"})
    
    @staticmethod
    def create_zip_with_files(files: dict[str, str]) -> BytesIO:
        """Creates a ZIP file in memory with the specified files and content"""
        import zipfile
        from io import BytesIO
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename, content in files.items():
                zip_file.writestr(filename, content)
        
        zip_buffer.seek(0)
        return zip_buffer
        

    @staticmethod
    def sample_excel_content(filename: Literal["single_sheet.xls", "two_sheets.xlsx"]) -> BytesIO:
        pwd = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(pwd, "..", "files", "xls", filename,), "rb") as f:
            b = f.read()
            return io.BytesIO(b)
        

    @staticmethod
    def fixture_file_contents(folder, filename) -> BytesIO:
        pwd = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(pwd, "..", "files", folder, filename), "rb") as f:
            b = f.read()
            return io.BytesIO(b)
        

    @staticmethod
    def sample_csv_data(data: List[List[str]]) -> StringIO:
        buffer = StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
        writer.writerows(data)
        return buffer

    @staticmethod
    def generate_rsa_keys() -> Tuple[bytes, bytes]:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return public_pem, private_pem

    @staticmethod
    def generate_gpg_keys(email: str = "example@example.com") -> Tuple[bytes, bytes, gnupg.GPG]:
        gpg = gnupg.GPG(gnupghome=os.environ["GNUPGHOME"])
        input_data = gpg.gen_key_input(name_email=email, key_type="RSA", key_length=1024, no_protection=True)

        key = gpg.gen_key(input_data)
        if not key:
            raise RuntimeError("Failed to generate a GPG key.")

        public = gpg.export_keys(key.fingerprint)
        private = gpg.export_keys(key.fingerprint, secret=True, expect_passphrase=False)

        return public.encode(), private.encode(), gpg

    @staticmethod
    def category_config(peer: str, category1: str, patterns1: List[str], transformations1: Optional[List[str]] = None,
                        category2: Optional[str] = None, patterns2: Optional[List[str]] = None) -> str:
        def to_category_item(category: str, patterns: List[str], 
                             transformations: Optional[List[str]] = None) -> Dict[str, Any]:
            return { "id": peer, "category_id": category, "filename_patterns": patterns, 
                    "transformations": transformations }

        categories = [ to_category_item(category=category1, patterns=patterns1, transformations = transformations1) ]
        if category2 and patterns2:
            categories.append(to_category_item(category=category2, patterns=patterns2))

        return json.dumps(categories)
    
    @staticmethod
    def peer_config(peer: str, type: Optional[str] = None, name: Optional[str] = None, method: Optional[str] = None, host_name: Optional[str] = None, port: Optional[int] = None, user_name: Optional[str] = None, folder: Optional[str] = None, ssh_pubk: Optional[str] = None, categories: Optional[List[Dict[str, Any]]] = None, fingerprints: Optional[List[str]] = None, timestamp_tagging: Optional[bool] = None) -> str:
        config = [{
            "id": peer,
            "type": type or "bank",
            "name": name or "peer name",
            "method": method or "push",
            "hostname": host_name or "host_name",
            "host-sha256-fingerprints": fingerprints or [],
            "port": port or 22,
            "username": user_name or "username",
            "folder": folder,
            "schedule": "0/1 * * * ? *",
            "ssh-public-key": ssh_pubk or "ssh-rsa AAAA",
            "add-timestamp-to-downloaded-files": timestamp_tagging or False,
            "categories": categories or list()
        }]
        return json.dumps(config)
    
    @staticmethod
    def api_peer_config(peer: str, name: Optional[str] = None, method: Optional[str] = None, categories: Optional[List[Dict[str, Any]]] = None, api_config: Optional[Dict[str, Any]] = None) -> str:
        if api_config is None:
            api_config = {
                "wise": {
                    "sub_accounts": ["123456789"]
                }
            }

        config = [{
            "id": peer,
            "name": name or "peer name",
            "method": method or "push",
            "schedule": "0/1 * * * ? *",
            "config": api_config,
            "categories": categories or list()
        }]
        return json.dumps(config)