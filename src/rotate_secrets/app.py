# Based on: https://github.com/aws-samples/aws-secrets-manager-rotation-lambdas/blob/master/SecretsManagerRotationTemplate/lambda_function.py

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Callable, Optional

from aws_lambda_typing.context import Context
from aws_lambda_typing.events import SecretsManagerRotationEvent
from clients import get_metric_client, get_secretsmanager_client, get_ssm_client
from entities.context_under_test import ContextUnderTest
from mypy_boto3_secretsmanager import SecretsManagerClient
from mypy_boto3_ssm import SSMClient
from utils.metrics import (
    MetricClient,
    metric_lambda_rotate_secrets_action,
    metric_lambda_rotate_secrets_create,
    metric_lambda_rotate_secrets_finish,
    metric_lambda_rotate_secrets_test,
)

from rotate_secrets.rotator import AbstractTokenRotator, ArchTokenRotator, SoftledgerTokenRotator

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(
    event: SecretsManagerRotationEvent, context: Context, test_context: Optional[ContextUnderTest] = None
) -> None:
    """Potentially performs rotation for the secret wrapped in the specified SecretsManagerRotationEvent, if the type
    of secret has an implementation in this handler.

    Args:
        event (dict): Lambda dictionary of event parameters. These keys must include the following:
            - SecretId: The secret ARN or identifier
            - ClientRequestToken: The ClientRequestToken of the secret version
            - Step: The rotation step (one of createSecret, setSecret, testSecret, or finishSecret)

        context (LambdaContext): The Lambda runtime information

        test_context (Optional[ContextUnderTest], optional): may be used in testing for dependency injection

    Raises:
        ResourceNotFoundException: If the secret with the specified arn and stage does not exist

        ValueError: If the secret is not properly configured for rotation

        KeyError: If the event parameters do not contain the expected keys

    """
    logger.info(f"Received event: {event}")
    execution_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())

    ssm_client = getattr(test_context, "ssm_client", None) or get_ssm_client()
    current_datetime = getattr(test_context, "current_datetime", lambda: datetime.now())
    metric_client = getattr(test_context, "metric_client", None) or get_metric_client(
        ssm_client=ssm_client, current_datetime=current_datetime
    )

    rotator = _select_rotator(rotator_type=os.environ.get("ROTATOR_TYPE"))

    arn = event["SecretId"]
    token = event["ClientRequestToken"]
    step = event["Step"]

    # Validate that rotation for the given secret is implemented in this function
    rotatable_secrets = {os.environ["ROTABLE_SECRET_ARN"]}
    if arn not in rotatable_secrets:
        metric_client.lambda_error(
            execution_id=execution_id, function_name="rotate_secrets", tags={"rotator_context": rotator.context()}
        )
        raise ValueError("Secret %s cannot be rotated using this function" % arn)

    try:
        secretsmanager_client = getattr(test_context, "secretsmanager_client", None) or get_secretsmanager_client()

        # Make sure the version is staged correctly
        logger.info(f"Getting metadata for secret: {arn}")
        metadata = secretsmanager_client.describe_secret(SecretId=arn)
        if not metadata["RotationEnabled"]:
            logger.error("Secret %s is not enabled for rotation" % arn)
            raise ValueError("Secret %s is not enabled for rotation" % arn)

        versions = metadata["VersionIdsToStages"]

        if token not in versions:
            logger.error("Secret version %s has no stage for rotation of secret %s." % (token, arn))
            raise ValueError("Secret version %s has no stage for rotation of secret %s." % (token, arn))

        if "AWSCURRENT" in versions[token]:
            logger.info("Secret version %s already set as AWSCURRENT for secret %s." % (token, arn))
            return
        elif "AWSPENDING" not in versions[token]:
            logger.error("Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))
            raise ValueError("Secret version %s not set as AWSPENDING for rotation of secret %s." % (token, arn))

        metric_client.rate(
            metric_name=metric_lambda_rotate_secrets_action, value=1, tags={"step": step, "secret": arn.split(":")[-1]}
        )

        if step == "createSecret":
            create_secret(
                secretsmanager_client=secretsmanager_client,
                ssm_client=ssm_client,
                metric_client=metric_client,
                rotator=rotator,
                secret_arn=arn,
                client_request_token=token,
                current_datetime=current_datetime,
            )
        elif step == "setSecret":
            set_secret(secretsmanager_client=secretsmanager_client, secret_arn=arn, client_request_token=token)

        elif step == "testSecret":
            test_secret(
                secretsmanager_client=secretsmanager_client,
                metric_client=metric_client,
                secret_arn=arn,
                client_request_token=token,
            )

        elif step == "finishSecret":
            finish_secret(
                secretsmanager_client=secretsmanager_client,
                metric_client=metric_client,
                secret_arn=arn,
                client_request_token=token,
            )

        else:
            raise ValueError("Invalid step parameter")

    except ValueError:
        metric_client.lambda_error(
            execution_id=execution_id, function_name="rotate_secrets", tags={"rotator_context": rotator.context()}
        )
        logger.exception("Lambda (rotate_secrets) failed.")
    except Exception as e:
        metric_client.lambda_error(
            execution_id=execution_id, function_name="rotate_secrets", tags={"rotator_context": rotator.context()}
        )
        logger.exception("Lambda (rotate_secrets) failed.")
        raise e


def create_secret(
    secretsmanager_client: SecretsManagerClient,
    ssm_client: SSMClient,
    metric_client: MetricClient,
    rotator: AbstractTokenRotator,
    secret_arn: str,
    client_request_token: str,
    current_datetime: Callable[[], datetime],
) -> None:
    """Create the secret

    This method first checks for the existence of a secret for the passed in token. If one does not exist, it will
    generate a new secret and put it with the passed in token.

    Args:
        secretsmanager_client (client): The secrets manager service client
        ssm_client (client): The Systems Manager service client
        metric_client (MetricClient): A client for shipping metrics
        rotator (AbstractTokenRotator): The rotator to be used against a specific token type
        secret_arn (string): The secret ARN or other identifier
        client_request_token (string): The ClientRequestToken associated with the secret version
        current_datetime (Callable[[], datetime]): a function to get the current time from
    Raises:
        ResourceNotFoundException: If the secret with the specified arn and stage does not exist

    """
    # Make sure the current secret exists
    logger.info("Making sure AWSCURRENT version stage exists.")
    response = secretsmanager_client.get_secret_value(SecretId=secret_arn, VersionStage="AWSCURRENT")

    # Checking if we can skip issuing a new auth token
    try:
        auth_token = json.loads(response["SecretString"])
        expiration = auth_token.get("expiration")
        if expiration:
            expiration_datetime = datetime.fromtimestamp(int(expiration))
            time_difference = expiration_datetime - current_datetime().replace(tzinfo=None)
            if not rotator.needs_refresh(time_left=time_difference):
                metric_client.rate(
                    metric_name=metric_lambda_rotate_secrets_create,
                    value=1,
                    tags={"status": "success", "secret": secret_arn.split(":")[-1]},
                )
                logger.info(f"Skipping rotation. Current auth token expires in: {time_difference}")
                return

        else:
            logger.warning("Stored auth token missing the 'expiration' field. Proceeding with rotation.")

    except (json.JSONDecodeError, TypeError):
        logger.warning("Currently stored authentication token is not valid json. Proceeding with rotation.")

    # Now try to get the AWSPENDING version, if that fails, issue a new secret otherwise exit
    try:
        logger.info("Assuming that AWSPENDING version stage does not yet exist.")
        secretsmanager_client.get_secret_value(
            SecretId=secret_arn, VersionId=client_request_token, VersionStage="AWSPENDING"
        )
        logger.info(f"createSecret: Successfully retrieved existing AWSPENDING version for secret: {secret_arn}")
    except secretsmanager_client.exceptions.ResourceNotFoundException:
        client_credentials = rotator.client_credentials(ssm_client=ssm_client)
        new_token = rotator.request_new_token(client_credentials=client_credentials, current_datetime=current_datetime)

        logger.info(f"About to store new token with expiration {new_token.valid_until} under AWSPENDING")

        # store new authentication token as AWSPENDING version, also add custom 'expiration' attribute
        secretsmanager_client.put_secret_value(
            SecretId=secret_arn,
            ClientRequestToken=client_request_token,
            SecretString=json.dumps({**new_token.secret_value, "expiration": new_token.valid_until}),
            VersionStages=["AWSPENDING"],
        )
        metric_client.rate(
            metric_name=metric_lambda_rotate_secrets_create,
            value=1,
            tags={"status": "success", "secret": secret_arn.split(":")[-1]},
        )
        logger.info(f"createSecret: Successfully put secret for ARN {secret_arn} + version id {client_request_token}.")


def set_secret(secretsmanager_client: SecretsManagerClient, secret_arn: str, client_request_token: str) -> None:
    """Set the secret

    This method should set the AWSPENDING secret in the service that the secret belongs to. For example, if the secret
    is a database credential, this method should take the value of the AWSPENDING secret and set the user's password to
    this value in the database.

    Not every service needs to implement this.

    Args:
        secretsmanager_client (client): The secrets manager service client

        metric_client (MetricClient): A client for shipping metrics

        secret_arn (string): The secret ARN or other identifier

        client_request_token (string): The ClientRequestToken associated with the secret version

    """
    # we don't need to do anything for our API integrations here
    pass


def test_secret(
    secretsmanager_client: SecretsManagerClient, metric_client: MetricClient, secret_arn: str, client_request_token: str
) -> None:
    """Test the secret

    This method should validate that the AWSPENDING secret works against the service that the secret belongs to. For
    example, if the secret is a database credential, this method should validate that the user can login with the
    password in AWSPENDING and that the user has all of the expected permissions against the database.

    If the test fails, this function should raise an exception. (any exception.)
    If no exception is raised, the test is considered to have passed. (The return value is ignored.)

    Args:
        secretsmanager_client (client): The secrets manager service client

        metric_client (MetricClient): A client for shipping metrics

        secret_arn (string): The secret ARN or other identifier

        client_request_token (string): The ClientRequestToken associated with the secret version

    """
    logger.info("Checking if create_secret put a value in AWSPENDING during this rotation, before issuing a test")
    try:
        response = secretsmanager_client.get_secret_value(
            SecretId=secret_arn, VersionId=client_request_token, VersionStage="AWSPENDING"
        )
        logger.info(f"Successfully retrieved existing AWSPENDING version for secret: {secret_arn}")
    except secretsmanager_client.exceptions.ResourceNotFoundException:
        # based on expiration, we might not have stored a value in the AWSPENDING version of the secret ..
        return

    rotator = _select_rotator(rotator_type=os.environ.get("ROTATOR_TYPE"))
    rotator.healthcheck(access_token=json.loads(response["SecretString"]))

    metric_client.rate(
        metric_name=metric_lambda_rotate_secrets_test,
        value=1,
        tags={"status": "success", "secret": secret_arn.split(":")[-1]},
    )


def finish_secret(
    secretsmanager_client: SecretsManagerClient, metric_client: MetricClient, secret_arn: str, client_request_token: str
) -> None:
    """Finish the secret

    This method finalizes the rotation process by marking the secret version passed in as the AWSCURRENT secret.

    Args:
        secretsmanager_client (client): The secrets manager service client

        secret_arn (string): The secret ARN or other identifier

        client_request_token (string): The ClientRequestToken associated with the secret version

    Raises:
        ResourceNotFoundException: If the secret with the specified arn does not exist

    """
    logger.info("Checking if rotation needs to be finished in case create_secret put an updated value in AWSPENDING.")
    try:
        secretsmanager_client.get_secret_value(
            SecretId=secret_arn, VersionId=client_request_token, VersionStage="AWSPENDING"
        )
        logger.info(f"Found existing AWSPENDING version for secret: {secret_arn}")
    except secretsmanager_client.exceptions.ResourceNotFoundException:
        # based on expiration, we might not have stored a value in the AWSPENDING version of the secret ..
        return

    # First describe the secret to get the current version
    metadata = secretsmanager_client.describe_secret(SecretId=secret_arn)
    current_version = None
    for version in metadata["VersionIdsToStages"]:
        if "AWSCURRENT" in metadata["VersionIdsToStages"][version]:
            if version == client_request_token:
                # The correct version is already marked as current, return
                logger.info("finishSecret: Version %s already marked as AWSCURRENT for %s" % (version, secret_arn))
                metric_client.rate(
                    metric_name=metric_lambda_rotate_secrets_finish,
                    value=1,
                    tags={"status": "success", "secret": secret_arn.split(":")[-1]},
                )
                return
            current_version = version
            break

    if current_version:  # Finalize by staging the secret version current
        secretsmanager_client.update_secret_version_stage(
            SecretId=secret_arn,
            VersionStage="AWSCURRENT",
            MoveToVersionId=client_request_token,
            RemoveFromVersionId=current_version,
        )

        metric_client.rate(
            metric_name=metric_lambda_rotate_secrets_finish,
            value=1,
            tags={"status": "success", "secret": secret_arn.split(":")[-1]},
        )
        logger.info(
            "finishSecret: Successfully set AWSCURRENT stage to version %s for secret %s."
            % (client_request_token, secret_arn)
        )


def _select_rotator(rotator_type: Optional[str]) -> AbstractTokenRotator:
    if rotator_type:
        context = os.environ.get("ROTATOR_CONTEXT")
        if rotator_type == "softledger":
            return SoftledgerTokenRotator(context=context)
        elif rotator_type == "arch":
            return ArchTokenRotator(context=context)

    raise ValueError(f"Unable to select rotator for type: {rotator_type}")
