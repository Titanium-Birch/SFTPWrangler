from io import StringIO

from dataclasses import dataclass
import logging
import os
import time
from typing import List
import typing

from paramiko import SFTPError, SSHClient, SSHException
import paramiko

from utils.sftp import SftpFileItem, convert_to_pkey, default_missing_host_key_policy


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def upload_file_into_sftp(host_name: str, user_name: str, private_key: str, remote_location: str, content: typing.BinaryIO, port: int=22) -> SftpFileItem:
    """Opens a connection to an SFTP server that is available using the specified parameters. Once connected, stores the specified `content` as
    a file at the `remote_location` in the SFTP server.

    Args:
        host_name (str): the host of the SFTP server
        user_name (str): the user name in the SFTP server
        private_key (str): a private key to be presented when connecting to the SFTP server
        remote_location (str): a file location inside the server
        content (BinaryIO): the file content
        port (int, optional): port of the SFTP server. Defaults to 22.        

    Returns:
        List[SftpFileItem]: existing files inside the server
    """
    try:
        pk = convert_to_pkey(input=private_key)
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(default_missing_host_key_policy())
            
            logger.info(f"About to connect to SFTP at {host_name}:{port} using username {user_name} and private key {private_key[:3]}***.")
            ssh.connect(host_name, username=user_name, pkey=pk, port=port)
            return _upload_file(ssh_client=ssh, remote_location=remote_location, content=content)
    except (SFTPError, SSHException):
        logger.exception(f"Unable to upload a file into the SFTP server at: {remote_location}")
        raise ValueError("Something failed uploading a file into the SFTP server.")
    

def _upload_file(ssh_client: SSHClient, remote_location: str, content: typing.BinaryIO) -> SftpFileItem:
    with ssh_client.open_sftp() as sftp:
        # make sure the directories exist
        directories = os.path.dirname(remote_location)
        try:
            sftp.stat(directories)
        except FileNotFoundError:
            sftp.mkdir(directories)

        logger.info(f"Storing file at: {remote_location} ...")
        sftp.putfo(fl=content, remotepath=remote_location)
        return SftpFileItem(filename=os.path.basename(remote_location), location=remote_location, size=-1, last_modified=int(time.time()))