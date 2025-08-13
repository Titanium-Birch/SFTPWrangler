import pytest

from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives import serialization

from utils.sftp import is_useable_private_key



class Test_SFTP_Module:

    @pytest.mark.unit
    def test_should_support_Ed25519_private_keys(self):
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption()
        )

        assert is_useable_private_key(input=private_key_pem.decode("utf-8")) is True


    @pytest.mark.unit
    def test_should_support_RSA_4096_bit_private_keys_in_OpenSSH_format(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )

        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        assert is_useable_private_key(input=private_key_bytes.decode("utf-8")) is True

