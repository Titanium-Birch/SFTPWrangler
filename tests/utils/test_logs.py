import pytest

from utils.logs import redacted_ssh_private_key


class Test_Logs_Module:

    @pytest.mark.unit
    def test_should_redact_private_keys(self):
        assert "" == redacted_ssh_private_key(potential_private_key=None)
        assert "" == redacted_ssh_private_key(potential_private_key="")
        assert "foo" == redacted_ssh_private_key(potential_private_key="foo")
        assert "fo**ar" == redacted_ssh_private_key(potential_private_key="foobar")
        assert "foob" == redacted_ssh_private_key(potential_private_key="foob")
        assert "ve***********ue" == redacted_ssh_private_key(potential_private_key="very long value")

        private_key = """-----BEGIN PRIVATE KEY-----
This is the actual private key.
It can be multiple lines.
-----END PRIVATE KEY-----
"""
        obfuscated = redacted_ssh_private_key(potential_private_key=private_key)
        assert "-----BEGIN PRIVATE KEY-----\nT******************************\n************************.\n-----END PRIVATE KEY-----" == obfuscated

        private_key_rsa = """-----BEGIN RSA PRIVATE KEY-----
This is the actual private key.
It can be multiple lines.
-----END RSA PRIVATE KEY-----
"""
        obfuscated = redacted_ssh_private_key(potential_private_key=private_key_rsa)
        assert "-----BEGIN RSA PRIVATE KEY-----\nT******************************\n************************.\n-----END RSA PRIVATE KEY-----" == obfuscated

        private_key_openssh = """-----BEGIN OPENSSH PRIVATE KEY-----
This is the actual OpenSSH private key.
It can be multiple lines.
-----END OPENSSH PRIVATE KEY-----
"""
        obfuscated = redacted_ssh_private_key(potential_private_key=private_key_openssh)
        assert "-----BEGIN OPENSSH PRIVATE KEY-----\nT**************************************\n************************.\n-----END OPENSSH PRIVATE KEY-----" == obfuscated

        private_key_encrypted = """-----BEGIN ENCRYPTED PRIVATE KEY-----
This is the actual OpenSSH private key.
It can be multiple lines.
-----END ENCRYPTED PRIVATE KEY-----
"""       
        obfuscated = redacted_ssh_private_key(potential_private_key=private_key_encrypted)
        assert "-----BEGIN ENCRYPTED PRIVATE KEY-----\nT**************************************\n************************.\n-----END ENCRYPTED PRIVATE KEY-----" == obfuscated