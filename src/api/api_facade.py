import io
import json
import logging
import os
import time
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, List, Literal, Optional, cast

import requests
from mypy_boto3_s3 import S3Client

from api.utils.datetime_range_calculator import DatetimeRange, DatetimeRangeCalculator
from utils.s3 import BucketItem, upload_file

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class ApiFacade:
    def execute(self: "ApiFacade", config: Dict[str, Any]) -> List[BucketItem]:
        return list()


class WiseApiFacade(ApiFacade):
    WISE_BASE_URL_PROD = "https://api.wise.com/v1"
    # https://docs.wise.com/api-docs/webhooks-notifications/event-handling
    WISE_PRODUCTION_PUB = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvO8vXV+JksBzZAY6GhSO
XdoTCfhXaaiZ+qAbtaDBiu2AGkGVpmEygFmWP4Li9m5+Ni85BhVvZOodM9epgW3F
bA5Q1SexvAF1PPjX4JpMstak/QhAgl1qMSqEevL8cmUeTgcMuVWCJmlge9h7B1CS
D4rtlimGZozG39rUBDg6Qt2K+P4wBfLblL0k4C4YUdLnpGYEDIth+i8XsRpFlogx
CAFyH9+knYsDbR43UJ9shtc42Ybd40Afihj8KnYKXzchyQ42aC8aZ/h5hyZ28yVy
Oj3Vos0VdBIs/gAyJ/4yyQFCXYte64I7ssrlbGRaco4nKF3HmaNhxwyKyJafz19e
HwIDAQAB
-----END PUBLIC KEY-----
"""

    WISE_BASE_URL_SANDBOX = "https://api.sandbox.transferwise.tech/v1"
    # https://docs.wise.com/api-docs/webhooks-notifications/event-handling
    WISE_SANDBOX_PUB = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwpb91cEYuyJNQepZAVfP
ZIlPZfNUefH+n6w9SW3fykqKu938cR7WadQv87oF2VuT+fDt7kqeRziTmPSUhqPU
ys/V2Q1rlfJuXbE+Gga37t7zwd0egQ+KyOEHQOpcTwKmtZ81ieGHynAQzsn1We3j
wt760MsCPJ7GMT141ByQM+yW1Bx+4SG3IGjXWyqOWrcXsxAvIXkpUD/jK/L958Cg
nZEgz0BSEh0QxYLITnW1lLokSx/dTianWPFEhMC9BgijempgNXHNfcVirg1lPSyg
z7KqoKUN0oHqWLr2U1A+7kqrl6O2nx3CKs1bj1hToT1+p4kcMoHXA7kA+VBLUpEs
VwIDAQAB
-----END PUBLIC KEY-----
"""

    def __init__(
        self, s3_client: S3Client, peer_id: str, api_key: str, range_calculator: DatetimeRangeCalculator
    ) -> None:
        super().__init__()
        self.s3_client = s3_client
        self.peer_id = peer_id
        self.api_key = api_key
        self.range_calc = range_calculator

    def execute(self: "WiseApiFacade", config: Dict[str, Any]) -> List[BucketItem]:
        """Fetches balance statements based on the specified config. The statements that
        contain at least one transaction will be uploaded to S3.

        Args:
            config (Dict[str, Any]): wise configuration from peers.json

        Raises:
            KeyError: if config does not denote a valid wise config

        Returns:
            _type_: list of BucketItem's which have been uploaded to S3
        """
        uploaded_files = list()

        ranges = self.range_calc.calculate()
        logger.info(
            f"Looking at statements: {','.join([f'{range.start_time_iso} - {range.end_time_iso}' for range in ranges])}"
        )

        profile = config["profile"]
        sub_accounts = config["sub_accounts"]
        if not sub_accounts:
            logger.warning(f"Profile {profile} for peer '{self.peer_id}' has no sub_accounts configured.")

        for sub_account in sub_accounts:
            for range in ranges:
                response = self._balance_statements(profile=profile, sub_account=sub_account, range=range)
                logger.info(f"Server responded with: {response}")

                transactions = response.get("transactions", [])
                if not transactions:
                    logger.info("No transactions found in the specified range. Not writing any output.")
                    continue

                object_key = self.assemble_object_key(
                    peer_id=self.peer_id,
                    profile=profile,
                    sub_account=sub_account,
                    type="balance_statement",
                    range=range,
                )
                upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]
                file_contents = json.dumps(response)
                uploaded_files.append(
                    upload_file(
                        client=self.s3_client,
                        bucket_name=upload_bucket,
                        key=object_key,
                        data=BytesIO(file_contents.encode("utf-8")),
                    )
                )

        return uploaded_files

    @staticmethod
    def assemble_object_key(peer_id: str, profile: str, sub_account: str, type: str, range: DatetimeRange) -> str:
        return f"{peer_id}/{profile}/{sub_account}_{type}_{range.start_time_iso}_{range.end_time_iso}.json"

    def _balance_statements(
        self: "WiseApiFacade", profile: str, sub_account: str, range: DatetimeRange
    ) -> Dict[str, Any]:
        """Fetches and returns the balance statements for the sub account in the given profile that
        falls within the specified (inclusive) date range.

        Args:
            profile (str): profile id of a wise account
            sub_account (str): account id from the wise account
            range (str): iso datetime range within which to fetch statements
        """
        if os.environ.get("ENVIRONMENT") == "staging":
            logger.info("Running against Wise sandbox ..")
            base_url = WiseApiFacade.WISE_BASE_URL_SANDBOX
        else:
            base_url = WiseApiFacade.WISE_BASE_URL_PROD

        url = (
            f"{base_url}/profiles/{profile}/balance-statements/{sub_account}/statement.json"
            f"?intervalStart={range.start_time_iso}&intervalEnd={range.end_time_iso}&type=COMPACT"
        )

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        logger.info(f"About to call GET {url} ...")

        try:
            response = requests.get(url=url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError:
            logger.error(f"Unable to fetch balance statements for profile {profile} and account {sub_account}.")
            raise ValueError("Unable to fetch balance statements.")
        except (ValueError, json.JSONDecodeError):
            logger.error("Unable to parse Wise response.")
            raise ValueError("Unable to parse Wise response.")


class ArchApiFacade(ApiFacade):
    ARCH_BASE_URL_PROD = "https://arch.co/client-api/v0"
    POINT_IN_TIME_RETRIEVABLE_ENTITIES = ("activities", "cash-flows", "tasks")
    ENTITIES_SUPPORTING_FILES = ("disabled_for_now",)
    ENTITIES_SUPPORTING_SUB_QUERIES = ("cash-flows", "tasks")
    SUB_QUERY_PREFIXES = ("due", "completed", "created")

    def __init__(
        self,
        s3_client: S3Client,
        peer_id: str,
        access_token: str,
        range_calculator: DatetimeRangeCalculator,
        rate_limit_handler: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self.s3_client = s3_client
        self.peer_id = peer_id
        self.access_token = access_token
        self.range_calc = range_calculator
        self.rate_limit_handler = rate_limit_handler or ArchApiFacade._default_rate_limit_handler

    @staticmethod
    def _default_rate_limit_handler(wait_time_seconds: int) -> None:
        """Sleeps for the specified number of seconds."""
        if wait_time_seconds >= 15 * 60:
            raise ValueError(f"Arch requested a wait of {wait_time_seconds} seconds, which exceeds AWS Lambda limits.")
        logger.warning(f"Handling rate limit. Waiting for {wait_time_seconds} seconds.")
        time.sleep(wait_time_seconds)

    @staticmethod
    def arch_peer_access_token_secret_id(peer_id: str) -> str:
        """Returns the name of a secret in AWS Secrets Manager, that contains the Arch access token for the
        peer having the given peer_id.

        Args:
            peer_id (str): the id of a peer

        Returns:
            str: name of an existing secret in AWS Secrets Manager
        """
        return f"/aws/reference/secretsmanager/lambda/rotate/{peer_id}/arch/auth"

    def execute(self: "ArchApiFacade", config: Dict[str, Any]) -> List[BucketItem]:
        """Fetches updates for the configured API resources.

        Args:
            config (Dict[str, Any]): wise configuration from peers.json

        Raises:
            KeyError: if config does not denote a valid Arch config

        Returns:
            _type_: list of BucketItem's which have been uploaded to S3
        """
        uploaded_files = list()

        entities = [entity for entity in config["entities"] if entity.get("enabled", False) is True]
        if not entities:
            logger.warning(f"Peer '{self.peer_id}' (Arch) has no entities configured that should be polled.")
            return []

        ranges = self.range_calc.calculate()
        ranges_fmt = ",".join([f"{range.start_time_iso} - {range.end_time_iso}" for range in ranges])
        logger.info(f"Looking at resources in range(s): {ranges_fmt}")

        for entity in entities:
            entity_name = entity.get("name", "")
            logger.info(f"Fetching {entity_name} ..")

            resource_name = entity["resource"]
            limit = int(entity.get("limit") or "25")  # Terraform might set limit: null

            if resource_name in ArchApiFacade.POINT_IN_TIME_RETRIEVABLE_ENTITIES:
                uploaded_files += self._process_point_in_time_entity(
                    resource_name=resource_name, limit=limit, ranges=ranges
                )
            else:
                uploaded_files += self._process_snapshot_entity(resource_name=resource_name, limit=limit)

        return uploaded_files

    def _process_snapshot_entity(self: "ArchApiFacade", resource_name: str, limit: int) -> List[BucketItem]:
        """Fetches an entity from Arch that does not support point in time recovery using date range parameters. Such
        an entity or resource is considered a snapshot entity.

        Args:
            resource_name (str): name of the entity or resource
            limit (int): defines the pagination page size

        Returns:
            List[BucketItem]: list of items that have been stored in S3
        """
        upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]

        files = []

        url = ArchApiFacade.resources_url(resource_name=resource_name, limit=limit)
        page = 0
        while url:
            page = page + 1
            if not url.startswith(ArchApiFacade.ARCH_BASE_URL_PROD):  # nextPage for pagination will be relative
                url = ArchApiFacade.ARCH_BASE_URL_PROD + url

            response = cast(Dict[str, Any], self._fetch(url=url, request_type="json"))
            logger.info(f"Server responded with: {response}")

            url = response.get("next")
            contents = response.get("contents", [])
            if not contents:
                logger.info("No contents found in the specified range. Not writing any output.")
                continue

            object_key = self.assemble_entities_snapshot_object_key(
                peer_id=self.peer_id, resource_name=resource_name, dt=self.range_calc.now(), page=page
            )
            file_contents = json.dumps(response)
            files.append(
                upload_file(
                    client=self.s3_client,
                    bucket_name=upload_bucket,
                    key=object_key,
                    data=BytesIO(file_contents.encode("utf-8")),
                )
            )

        return files

    def _process_point_in_time_entity(
        self: "ArchApiFacade", resource_name: str, limit: int, ranges: List[DatetimeRange]
    ) -> List[BucketItem]:
        """Fetches an entity from Arch that does support point in time recovery using date range parameters.

        Args:
            resource_name (str): name of the entity or resource
            limit (int): defines the pagination page size
            ranges (List[DatetimeRange]): the datetime ranges to be fetched

        Returns:
            List[BucketItem]: list of items that have been stored in S3
        """
        upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]

        files = []

        if resource_name in ArchApiFacade.ENTITIES_SUPPORTING_SUB_QUERIES:
            logger.info(f"{resource_name} is an entity which needs to be fetched with sub queries.")
            for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
                files += self._process_point_in_time_entity(
                    resource_name=f"{prefix}_{resource_name}", limit=limit, ranges=ranges
                )
        else:
            for range in ranges:
                page = 0

                url = ArchApiFacade.resources_url(
                    resource_name=resource_name,
                    limit=limit,
                    start_time_iso=range.start_time_iso,
                    end_time_iso=range.end_time_iso,
                )
                while url:
                    page = page + 1
                    if not url.startswith(ArchApiFacade.ARCH_BASE_URL_PROD):  # nextPage for pagination will be relative
                        url = ArchApiFacade.ARCH_BASE_URL_PROD + url

                    response = cast(Dict[str, Any], self._fetch(url=url, request_type="json"))
                    logger.info(f"Server responded with: {response}")

                    url = response.get("next")
                    contents = response.get("contents", [])
                    if not contents:
                        logger.info("No contents found in the specified range. Not writing any output.")
                        continue
                    elif resource_name in ArchApiFacade.ENTITIES_SUPPORTING_FILES:
                        files += self._process_entity_files(
                            entity_results=contents,
                            resource_name=resource_name,
                            base_name=range.file_base_name(),
                            page=page,
                        )

                    object_key = self.assemble_entities_in_range_object_key(
                        peer_id=self.peer_id, resource_name=resource_name, range=range, page=page
                    )
                    file_contents = json.dumps(response)
                    files.append(
                        upload_file(
                            client=self.s3_client,
                            bucket_name=upload_bucket,
                            key=object_key,
                            data=BytesIO(file_contents.encode("utf-8")),
                        )
                    )

        return files

    def _process_entity_files(
        self: "ArchApiFacade", entity_results: List[Dict[str, Any]], resource_name: str, base_name: str, page: int
    ) -> List[BucketItem]:
        files_bucket = os.environ["BUCKET_NAME_FILES"]
        upload_bucket = os.environ["BUCKET_NAME_UPLOAD"]

        files = []

        for entity in entity_results:
            entity_id = entity.get("id")
            if not entity_id:
                raise ValueError(f"Unable to download files for {resource_name} without an id.")

            files_url = self.files_url(entity_id=entity_id, resource_name=resource_name)
            files_response = cast(Dict[str, Any], self._fetch(url=files_url, request_type="json"))
            files_list = files_response.get("contents", [])
            if files_list:
                logger.info(f"Found {len(files_list)} file(s) for entity {entity_id} ({resource_name}).")
                metadata_key = self.assemble_file_metadata_key(
                    peer_id=self.peer_id,
                    resource_name=resource_name,
                    base_name=base_name,
                    entity_id=entity_id,
                    page=page,
                )
                metadata_contents = json.dumps(files_response)
                files.append(
                    upload_file(
                        client=self.s3_client,
                        bucket_name=upload_bucket,
                        key=metadata_key,
                        data=metadata_contents,
                    )
                )
                for x, file_metadata in enumerate(files_list):
                    download_url = file_metadata.get("downloadUrl")
                    if not download_url:
                        raise ValueError("Found a file that did not have a 'downloadUrl'.")
                    elif not download_url.startswith(ArchApiFacade.ARCH_BASE_URL_PROD):
                        download_url = ArchApiFacade.ARCH_BASE_URL_PROD + download_url

                    file_contents = cast(io.BytesIO, self._fetch(url=download_url, request_type="binary"))

                    file_key = self.assemble_file_object_key(
                        peer_id=self.peer_id,
                        resource_name=resource_name,
                        base_name=base_name,
                        page=page,
                        file_name=file_metadata.get("name", f"file{x}"),
                    )
                    files.append(
                        upload_file(
                            client=self.s3_client,
                            bucket_name=files_bucket,
                            key=file_key,
                            data=file_contents,
                        )
                    )

        return files

    @staticmethod
    def resources_url(
        resource_name: str, limit: int, start_time_iso: Optional[str] = None, end_time_iso: Optional[str] = None
    ) -> str:
        resource_url = f"{ArchApiFacade.ARCH_BASE_URL_PROD}/{resource_name}?limit={limit}"
        for sub_query_resource in ArchApiFacade.ENTITIES_SUPPORTING_SUB_QUERIES:
            for prefix in ArchApiFacade.SUB_QUERY_PREFIXES:
                if resource_name == f"{prefix}_{sub_query_resource}":
                    resource_url = f"{ArchApiFacade.ARCH_BASE_URL_PROD}/{sub_query_resource}?limit={limit}"

        if resource_name == "activities":
            params = f"&includeSummaries=true&afterProcessedAt={start_time_iso}&beforeProcessedAt={end_time_iso}"
        elif resource_name == "holdings":
            params = "&includeMetrics=true&includeCustomFields=true"
        elif resource_name == "due_cash-flows":
            params = f"&includeAllocations=true&afterDueAt={start_time_iso}&beforeDueAt={end_time_iso}"
        elif resource_name == "completed_cash-flows":
            params = f"&includeAllocations=true&afterCompletedAt={start_time_iso}&beforeCompletedAt={end_time_iso}"
        elif resource_name == "created_cash-flows":
            params = f"&includeAllocations=true&afterCreatedAt={start_time_iso}&beforeCreatedAt={end_time_iso}"
        elif resource_name == "due_tasks":
            params = f"&afterDueDate={start_time_iso}&beforeDueDate={end_time_iso}"
        elif resource_name == "completed_tasks":
            params = f"&afterCompletionDate={start_time_iso}&beforeCompletionDate={end_time_iso}"
        elif resource_name == "created_tasks":
            params = f"&afterCreationTime={start_time_iso}&beforeCreationTime={end_time_iso}"
        else:
            params = ""

        return f"{resource_url}{params}"

    @staticmethod
    def files_url(entity_id: str, resource_name: str) -> str:
        return f"{ArchApiFacade.ARCH_BASE_URL_PROD}/{resource_name}/{entity_id}/files"

    @staticmethod
    def assemble_entities_in_range_object_key(peer_id: str, resource_name: str, range: DatetimeRange, page: int) -> str:
        basename = range.file_base_name()
        return f"{peer_id}/{resource_name}_{basename}_{page}.json"

    @staticmethod
    def assemble_entities_snapshot_object_key(peer_id: str, resource_name: str, dt: datetime, page: int) -> str:
        basename = dt.strftime("%Y%m%d")
        return f"{peer_id}/{resource_name}_{basename}_{page}.json"

    @staticmethod
    def assemble_file_metadata_key(peer_id: str, resource_name: str, entity_id: str, base_name: str, page: int) -> str:
        return f"{peer_id}/{resource_name}_{base_name}_{page}_{entity_id}_files.json"

    @staticmethod
    def assemble_file_object_key(peer_id: str, resource_name: str, base_name: str, page: int, file_name: str) -> str:
        return f"{peer_id}/{resource_name}_{base_name}_{page}/{file_name}"

    def _fetch(self: "ArchApiFacade", url: str, request_type: Literal["json", "binary"]) -> Dict[str, Any] | io.BytesIO:
        """Fetches and returns the response (wrapped or unwrapped) using the given url.

        Args:
            url (str): the full url to request Arch with
            request_type (Literal): sets the type of request to be either json or binary
        """
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        logger.info(f"About to call GET {url} ...")

        try:
            if request_type == "json":
                response = requests.get(url=url, headers=headers)
                response.raise_for_status()
                return response.json()
            else:
                response = requests.get(url=url, headers=headers, stream=True)
                response.raise_for_status()
                return io.BytesIO(response.content)
        except requests.HTTPError as http_err:
            if response.status_code == 429:
                logger.info(f"Arch responded with status code 429. Headers: {response.headers}")
                retry_after = response.headers.get("ratelimit-reset")
                if retry_after:
                    try:
                        self.rate_limit_handler(int(retry_after))
                        return self._fetch(url=url, request_type=request_type)
                    except ValueError:
                        logger.error("Invalid ratelimit-reset header value.")
                        raise ValueError("Invalid ratelimit-reset header value.")
                else:
                    logger.error("429 received but no ratelimit-reset header found.")
                    raise ValueError("Rate limit exceeded without retry information.")
            else:
                logger.error(f"GET request failed. HTTP error: {http_err}")
                raise ValueError("Error calling Arch.")
        except (ValueError, json.JSONDecodeError) as parse_err:
            logger.error(f"Unable to parse response for Arch. Error: {parse_err}")
            raise ValueError("Unable to parse response for Arch.")
