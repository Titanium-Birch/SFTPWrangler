import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import requests
from mypy_boto3_ssm import SSMClient

from rotate_secrets.entities.rotating_token import RotatingToken

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class AbstractTokenRotator(ABC):
    def client_credentials(self: "AbstractTokenRotator", ssm_client: SSMClient) -> str:
        """Fetches and returns client credentials from AWS Systems Manager. The
        SSM key to the credentials is expected to be stored in an environment
        variable called SSM_KEY_CLIENT_CREDENTIALS.

        Args:
            ssm_client (SSMClient): the AWS Systems Manager client

        Returns:
            str: the (json) string denoting client credentials for this rotator
        """
        client_credentials_ssm_key = os.environ["SSM_KEY_CLIENT_CREDENTIALS"]
        logger.info(f"About to get client credentials stored under SSM key: {client_credentials_ssm_key}")

        parameter = ssm_client.get_parameter(Name=client_credentials_ssm_key, WithDecryption=True)
        return parameter.get("Parameter", {}).get("Value", "")

    @abstractmethod
    def request_new_token(
        self: "AbstractTokenRotator", client_credentials: str, current_datetime: Callable[[], datetime]
    ) -> RotatingToken:
        """Subclasses must implement this to create a new API specific access token"""
        pass

    @abstractmethod
    def healthcheck(self: "AbstractTokenRotator", access_token: Dict[str, Any]) -> None:
        """Subclasses must implement this to issue a health check against the API"""
        pass

    @abstractmethod
    def needs_refresh(self: "AbstractTokenRotator", time_left: timedelta) -> bool:
        """Subclasses must implement this to return True if the token needs a refresh"""
        pass

    @abstractmethod
    def context(self: "AbstractTokenRotator") -> str:
        """Returns the context in which the rotator was executed"""
        pass


class SoftledgerTokenRotator(AbstractTokenRotator):
    def __init__(self, context: Optional[str] = None) -> None:
        super().__init__()
        self.ctx = context

    def request_new_token(
        self: "SoftledgerTokenRotator", client_credentials: str, current_datetime: Callable[[], datetime]
    ) -> RotatingToken:
        logger.info("Issuing new Softledger authentication token.")
        try:
            response = requests.post(
                "https://auth.accounting-auth.com/oauth/token",
                json=json.loads(client_credentials),
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.exception("Unable to issue Softledger authentication token.")
            raise e

        authentication_token = response.json()
        logger.info(f"Softledger responded with: {dict({**authentication_token, 'access_token':'***'})}")

        next_expiration = int(current_datetime().timestamp() + authentication_token["expires_in"])
        return RotatingToken(secret_value=authentication_token, valid_until=next_expiration)

    def healthcheck(self: "SoftledgerTokenRotator", access_token: Dict[str, Any]) -> None:
        logger.info(
            f"Healthchecking Softledger using token expiring {access_token.get("expiration", "missing")}, "
            + "stored under AWSPENDING"
        )
        headers = {"Authorization": f"Bearer {access_token.get("access_token")}"}

        response = requests.get("https://api.softledger.com/v2/webhooks", headers=headers)
        response.raise_for_status()

        logger.info(f"Softledger responded with status: {response.status_code}")

    def needs_refresh(self: "SoftledgerTokenRotator", time_left: timedelta) -> bool:
        return time_left <= timedelta(hours=8)

    def context(self: "SoftledgerTokenRotator") -> str:
        return self.ctx or "missing"


class ArchTokenRotator(AbstractTokenRotator):
    def __init__(self, context: Optional[str] = None) -> None:
        super().__init__()
        self.ctx = context

    def request_new_token(
        self: "ArchTokenRotator", client_credentials: str, current_datetime: Callable[[], datetime]
    ) -> RotatingToken:
        logger.info("Issuing new Arch access token.")
        try:
            response = requests.post(
                "https://arch.co/client-api/v0/auth/token",
                json=json.loads(client_credentials),
            )
            response.raise_for_status()
        except json.decoder.JSONDecodeError:
            logger.exception("Invalid client credentials.")
            raise ValueError("Please set up the client credentials for creating a new access token for Arch.")
        except requests.HTTPError:
            logger.exception("Arch responded with an error.")
            raise ValueError("Unable to create new token for Arch.")

        access_token = response.json()
        logger.info(f"Arch responded with: {dict({**access_token, 'accessToken':'***'})}")

        next_expiration = int(current_datetime().timestamp() + access_token["expiresIn"])
        return RotatingToken(secret_value=access_token, valid_until=next_expiration)

    def healthcheck(self: "ArchTokenRotator", access_token: Dict[str, Any]) -> None:
        logger.info(
            f"Healthchecking Arch using token expiring {access_token.get("expiration", "missing")}, "
            + "stored under AWSPENDING"
        )
        headers = {"Authorization": f"Bearer {access_token.get("accessToken")}"}

        response = requests.get("https://arch.co/client-api/v0/user-roles", headers=headers)
        response.raise_for_status()

        logger.info(f"Arch responded with status: {response.status_code}")

    def needs_refresh(self: "ArchTokenRotator", time_left: timedelta) -> bool:
        return time_left <= timedelta(hours=8)

    def context(self: "ArchTokenRotator") -> str:
        return self.ctx or "missing"
