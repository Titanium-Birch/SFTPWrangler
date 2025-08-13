from dataclasses import dataclass

from dataclasses_json import DataClassJsonMixin


@dataclass
class SftpPullEvent(DataClassJsonMixin):
    id: str

    def pgp_private_key_secret_id(self: "SftpPullEvent") -> str:
        return f"/aws/reference/secretsmanager/lambda/on_upload/pgp/{self.id}"
