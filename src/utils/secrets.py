import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

from botocore.client import BaseClient
from botocore.exceptions import ClientError
from dataclasses_json import DataClassJsonMixin, config

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


@dataclass
class SecretMetadata(DataClassJsonMixin):
    rotation_enabled: bool = field(metadata=config(field_name="RotationEnabled"))
    version_ids_to_stages: Dict[str, List[str]] = field(metadata=config(field_name="VersionIdsToStages"))


def fetch_parameter_value(client: BaseClient, parameter_id: str) -> str:
    """Fetches a String parameter using the specified SSM client.

    Args:
        client (BaseClient): the SSM client to use for fetching the secret
        parameter_id (str): the id of the parameter value to fetch

    Raises:
        ValueError: in case of an error fetching the parameter from AWS Secrets Manager

    Returns:
        str: the value in plain text
    """
    return fetch_secret(client=client, secret_id=parameter_id, with_decryption=False)


def fetch_secret(client: BaseClient, secret_id: str, with_decryption: bool = True) -> str:
    """Fetches a confidential value using the specified SSM client.

    Args:
        client (BaseClient): the SSM client to use for fetching the secret
        secret_id (str): the name of the secret to fetch
        with_decryption (bool): decrypt the parameter value?

    Raises:
        ValueError: in case of an error fetching the secret from AWS Secrets Manager

    Returns:
        str: the confidential value in plain text
    """
    logger.info(f"Looking up secret value using SSM parameter named: {secret_id}")

    try:
        parameter = client.get_parameter(Name=secret_id, WithDecryption=with_decryption)
        return parameter.get("Parameter", {}).get("Value")
    except ClientError as e:
        logger.exception(
            "Unable to get SSM parameter: %s. %s" % (secret_id, e.response.get("Error", {}).get("Message"))
        )
        raise ValueError(f"Unable to fetch parameter {secret_id} from AWS Secrets Manager.")
