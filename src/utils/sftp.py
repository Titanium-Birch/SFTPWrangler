import inspect
import io
import logging
import os
import typing
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from typing import Callable, List, Optional

import paramiko
from dataclasses_json import DataClassJsonMixin
from paramiko import MissingHostKeyPolicy, PKey, SFTPAttributes, SFTPError, SSHClient, SSHException

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("paramiko").setLevel(logging.WARNING)


@dataclass
class SftpFileItem(DataClassJsonMixin):
    filename: str
    location: str
    size: Optional[int]
    last_modified: Optional[int]

    def convert_to_object_key(self: "SftpFileItem") -> str:
        if self.location:
            return self.location.lstrip("./")
        else:
            return self.location


class RejectFingerprintMismatchesPolicy(MissingHostKeyPolicy):
    """Auto-rejecting policy which raises an SSHException because the server failed to present
    the expected fingerprint.
    """

    def missing_host_key(
        self: "RejectFingerprintMismatchesPolicy", client: SSHClient, hostname: str, key: PKey
    ) -> None:
        raise SSHException("Server {!r} failed to present one of the configured fingerprints.".format(hostname))


class FingerprintVerificationPolicy(MissingHostKeyPolicy):
    """Marker interface to denote classes that implement fingerprint verification."""

    def log_fingerprint_match(self: "FingerprintVerificationPolicy", raw_multiline_message: str) -> None:
        """Normalize and logs the given raw multi-line string as a single line.

        Args:
            raw_multiline_message (str): a multi-line string
        """
        message = " ".join(inspect.cleandoc(raw_multiline_message).split())
        logger.info(message)


class FingerprintEnforcingPolicy(FingerprintVerificationPolicy):
    """Paramiko uses the `MissingHostKeyPolicy` interface to provide extension points to execute custom logic when new
    keys are encountered. We are leveraging this to verify that fingerprints presented by the server match what we have
    configured for the peer.

    Args:
        MissingHostKeyPolicy (_type_): see https://docs.paramiko.org/en/2.4/api/client.html#paramiko.client.MissingHostKeyPolicy
    """

    def __init__(self: "FingerprintEnforcingPolicy", peer_id: str, allowed_fingerprints: List[str]) -> None:
        self.peer_id = peer_id
        self.allowed_fingerprints = allowed_fingerprints
        self.rejection_policy = RejectFingerprintMismatchesPolicy()

    def missing_host_key(self: "FingerprintEnforcingPolicy", client: SSHClient, hostname: str, key: PKey) -> None:
        fingerprint_sha256 = self._sha256_fingerprint(key=key)
        fingerprint_found = fingerprint_sha256 in self.allowed_fingerprints
        fingerprint_match_message = f"""\
            Server for peer: {self.peer_id} and host: {hostname} ({key.get_name()}) presented \
            fingerprint: {fingerprint_sha256}. Our expected fingerprints are: {self.allowed_fingerprints}. \
            Therefore, we have a {"FINGERPRINT MATCH" if fingerprint_found else "FINGERPRINT MISMATCH"}."""

        self.log_fingerprint_match(raw_multiline_message=fingerprint_match_message)

        policy = self._missing_host_key_policy(fingerprint_found=fingerprint_found)
        policy.missing_host_key(client=client, hostname=hostname, key=key)

    def _sha256_fingerprint(self: "FingerprintEnforcingPolicy", key: PKey) -> str:
        return key.fingerprint  # type: ignore

    def _missing_host_key_policy(self: "FingerprintEnforcingPolicy", fingerprint_found: bool) -> MissingHostKeyPolicy:
        return default_missing_host_key_policy() if fingerprint_found else self.rejection_policy


class FingerprintIgnoringPolicy(FingerprintVerificationPolicy):
    def missing_host_key(self: "FingerprintIgnoringPolicy", client: SSHClient, hostname: str, key: PKey) -> None:
        policy = default_missing_host_key_policy()
        policy.missing_host_key(client=client, hostname=hostname, key=key)


def default_missing_host_key_policy() -> MissingHostKeyPolicy:
    """Returns the default policy, that will be used for SFTP operations when we encounter an unknown host key and
    the caller did not specify a custom policy.

    Returns:
        MissingHostKeyPolicy: our default policy to deal with unknown host keys
    """
    return paramiko.AutoAddPolicy()


def is_useable_private_key(input: str) -> bool:
    """Returns True of the given input denotes a valid private key string value in a format that we support.

    Args:
        input (str): a string value that might or might not be a useable private key

    Returns:
        bool: True if given `input` is considered to be a private key in the correct syntax and format that we support
    """
    return convert_to_pkey(input=input) is not None


@staticmethod
def convert_to_pkey(input: str) -> Optional[PKey]:
    """Attempts to convert the given `input` string into a `PKey` instance for paramiko. Returns None if the input
    cannot be converted - either because it is invalid or we don't support the format.

    Args:
        input (str): a string value that might or might not be a private key

    Returns:
        Optional[PKey]: a PKey or None
    """
    if not input:
        return None

    for pkey_class in (paramiko.RSAKey, paramiko.DSSKey, paramiko.ECDSAKey, paramiko.Ed25519Key):
        try:
            return pkey_class.from_private_key(StringIO(input))
        except SSHException:
            pass

    return None


def download_new_files(
    sftp_user: str,
    sftp_host: str,
    sftp_port: int,
    ssh_private_key: str,
    remote_folder: Optional[str],
    download_eligable: Callable[[SftpFileItem], bool],
    download_handler: Callable[[SftpFileItem, typing.BinaryIO], None],
    missing_host_key_policy: Optional[MissingHostKeyPolicy] = None,
) -> List[SftpFileItem]:
    """Connects to SFTP, identifies and downloads new files.

    Args:
        sftp_user (str): the user name in the SFTP server
        sftp_host (str): the host of the SFTP server
        sftp_port (int, optional): port of the SFTP server. Defaults to 22.
        ssh_private_key (str): sftp private key
        remote_folder (Optional[str], optional): a folder location inside the server. Defaults to None.
        download_eligable (Callable[[SftpFileItem], bool]): function to check if a file shall be downloaded
        download_handler (Callable[[SftpFileItem, typing.BinaryIO], None]): callback function to handle the download
    Returns:
        List[SftpFileItem]: list of downloaded files
    """
    if not missing_host_key_policy:
        missing_host_key_policy = default_missing_host_key_policy()

    try:
        pk = convert_to_pkey(input=ssh_private_key)
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(missing_host_key_policy)

            logger.info(
                f"""About to connect to SFTP at {sftp_host}:{sftp_port} using username {sftp_user} and 
                private key {ssh_private_key[:3]}***."""
            )
            ssh.connect(sftp_host, username=sftp_user, pkey=pk, port=sftp_port)

            items = _list_folder(ssh_client=ssh, remote_folder=remote_folder)
            logger.info(f"Found {len(items)} file(s) in SFTP.")
            logger.debug(f"Files found: {[item.location for item in items]}")

            download_candidates = [item for item in items if download_eligable(item)]
            logger.info(f"Identified {len(download_candidates)} new file(s) to pull.")

            return _visit_files_using_client(
                ssh_client=ssh, sftp_file_items=download_candidates, callback=download_handler
            )

    except (SFTPError, SSHException):
        logger.exception(f"Unable to download new files in SFTP: {sftp_host}")
        raise ValueError("Something failed downloading new files in SFTP.")


def _list_folder(ssh_client: SSHClient, remote_folder: Optional[str] = None) -> List[SftpFileItem]:
    sftp_files = []
    with ssh_client.open_sftp() as sftp:
        path = remote_folder or "."
        remote_files: list[SFTPAttributes] = sftp.listdir_attr(path=path)
        remote_files = [remote_file for remote_file in remote_files if not remote_file.filename.startswith(".")]

        for remote_file in remote_files:
            if remote_file.longname and remote_file.longname.startswith("d"):
                logger.info(f"Entering directory {path}/{remote_file.filename} ...")
                sftp_files = sftp_files + _list_folder(
                    ssh_client=ssh_client, remote_folder=f"{path}/{remote_file.filename}"
                )
            else:
                sftp_item = SftpFileItem(
                    filename=remote_file.filename,
                    location=f"{path}/{remote_file.filename}",
                    size=remote_file.st_size,
                    last_modified=remote_file.st_mtime,
                )
                sftp_files.append(sftp_item)

    return sftp_files


def _visit_files_using_client(
    ssh_client: SSHClient,
    sftp_file_items: List[SftpFileItem],
    callback: Callable[[SftpFileItem, typing.BinaryIO], None],
) -> List[SftpFileItem]:
    response = []
    with ssh_client.open_sftp() as sftp:
        for sftp_file_item in sftp_file_items:
            logger.info(f"Fetching remote file: {sftp_file_item.location} ...")
            try:
                with sftp.open(sftp_file_item.location, "rb") as f:
                    logger.info("Found. Reading file content and invoking callback ...")
                    try:
                        b = f.read()
                        callback(sftp_file_item, io.BytesIO(b))
                        response.append(sftp_file_item)
                    except ValueError:
                        logger.warn(f"Something failed processing downloaded file: {sftp_file_item.location}")
            except IOError:
                logger.exception(f"Unable to open file: {sftp_file_item.location} in SFTP.")

    return response


def assemble_object_key(
    peer_id: str, timestamp_tagging: bool, current_datetime: Callable[[], datetime], sftp_file_item: SftpFileItem
) -> str:
    """Creates an S3 object key combining the given `peer_id` and `location` in the `SftpFileItem`. If
    `timestamp_tagging` is True, the current timestamp will be inserted before the file extension.

    Args:
        peer_id (str): the id of a bank or broker
        timestamp_tagging (str): True if a timestamp shall be inserted before the file extension
        current_datetime (Callable[[], datetime]): a function to get the current time from
        sftp_file_item (SftpFileItem): a file inside an SFTP server

    Returns:
        str: a string that can be used as the object key of an S3 object
    """
    if timestamp_tagging:
        object_key = insert_timestamp(
            file_name=sftp_file_item.convert_to_object_key(), current_datetime=current_datetime, use_sgt=True
        )
    else:
        object_key = sftp_file_item.convert_to_object_key()

    return f"{peer_id}/{object_key}"


def insert_timestamp(file_name: str, current_datetime: Callable[[], datetime], use_sgt: bool = False) -> str:
    """Inserts a formatted timestamp before the extension into the specified `file_name`.

    Args:
        file_name (str): any file name
        current_datetime (Callable[[], datetime]): a function to get the current time from
        use_sgt (bool, optional): True if the timestamp should denote SGT instead of UTC. Defaults to False.

    Returns:
        str: the modified filename with the formatted timestamp inserted
    """
    base_name, file_extension = os.path.splitext(file_name)

    now = current_datetime()
    offset_hours = 8 if use_sgt else 0
    dt = now + timedelta(hours=offset_hours)

    dt_formatted = dt.strftime(f"%Y-%m-%d_%H-%M-%S_{'SGT' if use_sgt else 'UTC'}")

    return f"{base_name}_({dt_formatted}){file_extension}"
