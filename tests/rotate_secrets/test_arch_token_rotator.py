from datetime import datetime
import pytest
from requests.models import HTTPError
from requests_mock import Mocker
from test_utils.fixtures import Fixtures

from rotate_secrets.rotator import ArchTokenRotator


current_datetime = Fixtures.fixed_datetime()


class Test_Arch_Token_Rotator:
    @pytest.mark.unit
    def test_should_raise_if_arch_responds_with_error(self, requests_mock: Mocker):
        requests_mock.post("https://arch.co/client-api/v0/auth/token", status_code=500)

        rotator = ArchTokenRotator()
        with pytest.raises(ValueError) as error:
            rotator.request_new_token(client_credentials="{}", current_datetime=lambda: datetime.now())
        assert str(error.value) == "Unable to create new token for Arch."

    @pytest.mark.unit
    def test_should_raise_if_client_credentials_are_not_json(self):
        rotator = ArchTokenRotator()
        with pytest.raises(ValueError) as error:
            rotator.request_new_token(client_credentials="foobar", current_datetime=lambda: datetime.now())
        assert str(error.value) == "Please set up the client credentials for creating a new access token for Arch."

    @pytest.mark.unit
    def test_should_issue_new_arch_token_and_calculate_expiration(self, requests_mock: Mocker):
        response = {"accessToken": "abc", "expiresIn": 1000}
        requests_mock.post("https://arch.co/client-api/v0/auth/token", json=response)

        rotator = ArchTokenRotator()
        rotating_token = rotator.request_new_token(client_credentials="{}", current_datetime=lambda: current_datetime)
        assert rotating_token.secret_value["accessToken"] == "abc"
        assert rotating_token.valid_until == int(current_datetime.timestamp() + 1000)

    @pytest.mark.unit
    def test_should_fail_healthcheck_if_arch_responds_with_error(self, requests_mock: Mocker):
        requests_mock.get("https://arch.co/client-api/v0/user-roles", headers={"Authorization": "Bearer abc"}, status_code=500)

        rotator = ArchTokenRotator()
        with pytest.raises(HTTPError):
            rotator.healthcheck(access_token={"accessToken": "abc"})

    @pytest.mark.unit
    def test_should_healthcheck_successfully(self, requests_mock: Mocker):
        requests_mock.get("https://arch.co/client-api/v0/user-roles", headers={"Authorization": "Bearer abc"}, status_code=500)

        rotator = ArchTokenRotator()
        with pytest.raises(HTTPError):
            rotator.healthcheck(access_token={"accessToken": "abc"})