import json
import importlib
import os
from io import BytesIO
from unittest.mock import MagicMock, call, patch

from botocore.exceptions import ClientError
import pytest
from requests import Response

os.environ["AWS_ACCOUNT_NAME"] = "test"
os.environ["GITHUB_ORG"] = "test-org"
os.environ["GITHUB_CLIENT_ID_SECRET_NAME"] = "client-id-secret"
os.environ["GITHUB_PRIVATE_KEY_SECRET_NAME"] = "private-key-secret"
os.environ["ALERT_SECRET_NAME"] = "alert-secret"
os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

alert_secret_values = {
    "azure_tenant_id": "tenant-id",
    "azure_client_id": "client-id",
    "azure_client_secret": "client-secret",
    "azure_webhook_url": "https://example.com/webhook",
    "channel_id": "channel-id",
}

mock_s3 = MagicMock()
mock_secret_manager = MagicMock()
mock_session = MagicMock()
mock_session.client.side_effect = lambda service, **kwargs: {
    "s3": mock_s3,
    "secretsmanager": mock_secret_manager,
}[service]
mock_secret_manager.get_secret_value.return_value = {
    "SecretString": json.dumps(alert_secret_values)
}

with patch("boto3.Session", return_value=mock_session), patch("keh_teams_alert.TeamsAlertClient"):
    from src.main import (
        BUCKET_NAME,
        get_and_update_historic_usage,
        handler,
        update_s3_object,
        get_dict_value,
        get_config_file,
    )


def reload_main_with_alert_secret(secret: str):
    module = importlib.import_module("src.main")
    session = MagicMock()
    secret_manager = MagicMock()
    secret_manager.get_secret_value.return_value = {"SecretString": secret}
    session.client.side_effect = lambda service, **kwargs: {
        "s3": MagicMock(),
        "secretsmanager": secret_manager,
    }[service]

    with patch("boto3.Session", return_value=session), patch("keh_teams_alert.TeamsAlertClient"):
        return importlib.reload(module)


# Mock GitHub API response
api_response = {
    "download_links": ["https://example.com/organisation_history_api_response.json"]
    # There are other fields in the API response, but we don't need them for testing
}

# Mock usage data fetched from download_links key in the API response
fetched_usage_data = {
    "day_totals": [
        {"day": "2024-01-01", "usage": 10},
        {"day": "2024-01-02", "usage": 20},
    ]
}


class TestUpdateS3Object:
    def test_update_s3_object_success(self, caplog):
        s3_client = MagicMock()
        bucket_name = "test-bucket"
        object_name = "test.json"
        data = {"foo": "bar"}

        caplog.set_level("INFO")  # Ensure INFO logs are captured

        update_s3_object(s3_client, bucket_name, object_name, data)

        s3_client.put_object.assert_called_once()
        args, kwargs = s3_client.put_object.call_args
        assert kwargs["Bucket"] == bucket_name
        assert kwargs["Key"] == object_name
        assert kwargs["Body"] == b'{\n    "foo": "bar"\n}'

        assert any("Successfully updated" in record.getMessage() for record in caplog.records)

    def test_update_s3_object_failure(self, caplog):
        s3_client = MagicMock()
        s3_client.put_object.side_effect = ClientError(
            error_response={"Error": {"Code": "500", "Message": "InternalError"}},
            operation_name="PutObject",
        )
        bucket_name = "test-bucket"
        object_name = "test.json"
        data = {"foo": "bar"}

        update_s3_object(s3_client, bucket_name, object_name, data)

        assert s3_client.put_object.called
        assert any("Failed to update" in record.message for record in caplog.records)
        from src.main import alerts_client

        alerts_client.post_to_webhook.assert_called_once()


class TestHandler:
    def test_handler_requires_client_id_secret_name(self):
        with (
            patch("src.main.client_id_secret_name", None),
            pytest.raises(ValueError, match="CLIENT_ID_SECRET_NAME"),
        ):
            handler({}, MagicMock())

    def test_handler_requires_private_key_secret_name(self):
        with (
            patch("src.main.private_key_secret_name", None),
            pytest.raises(ValueError, match="PRIVATE_KEY_SECRET_NAME"),
        ):
            handler({}, MagicMock())

    def test_handler_requires_client_id_in_secret(self):
        with (
            patch("src.main.secret_manager") as mock_secret_manager,
            pytest.raises(ValueError, match="Failed to retrieve ClientID"),
        ):
            mock_secret_manager.get_secret_value.return_value = {"SecretString": json.dumps({})}
            handler({}, MagicMock())

    def test_handler_requires_private_key_in_secret(self):
        with (
            patch("src.main.secret_manager") as mock_secret_manager,
            pytest.raises(ValueError, match="Failed to retrieve private key"),
        ):
            mock_secret_manager.get_secret_value.side_effect = [
                {"SecretString": json.dumps({"ClientID": "client-id"})},
                {"SecretString": ""},
            ]
            handler({}, MagicMock())

    @patch("src.main.github_api_toolkit.get_token_as_installation")
    @patch("src.main.github_api_toolkit.github_interface")
    @patch("src.main.get_and_update_historic_usage")
    def test_handler_success(
        self,
        mock_get_and_update_historic_usage,
        mock_github_interface,
        mock_get_token_as_installation,
        caplog,
    ):
        mock_s3 = MagicMock()
        mock_secret_manager = MagicMock()
        mock_secret_manager.get_secret_value.side_effect = [
            {"SecretString": json.dumps({"ClientID": "client-id"})},
            {"SecretString": "pem-content"},
        ]
        mock_get_token_as_installation.return_value = ("token",)
        mock_gh = MagicMock()
        mock_github_interface.return_value = mock_gh

        mock_get_and_update_historic_usage.return_value = (["usage1", "usage2"], ["2024-01-01"])

        with (
            patch("src.main.s3", mock_s3),
            patch("src.main.secret_manager", mock_secret_manager),
            patch("src.main.alerts_client") as mock_alerts,
        ):
            result = handler({}, MagicMock())

        assert result == "Github Data logging is now complete."
        assert mock_secret_manager.get_secret_value.call_args_list == [
            call(SecretId="client-id-secret"),
            call(SecretId="private-key-secret"),
        ]
        mock_get_token_as_installation.assert_called_once_with(
            "test-org", "pem-content", "client-id"
        )
        mock_github_interface.assert_called_once_with("token")
        mock_get_and_update_historic_usage.assert_called_once_with(mock_s3, mock_gh, False)
        mock_alerts.post_to_webhook.assert_called_once()

    @patch("src.main.github_api_toolkit.get_token_as_installation")
    def test_handler_access_token_error(self, mock_get_token_as_installation, caplog):
        mock_secret_manager = MagicMock()
        mock_secret_manager.get_secret_value.side_effect = [
            {"SecretString": json.dumps({"ClientID": "client-id"})},
            {"SecretString": "pem-content"},
        ]
        mock_get_token_as_installation.return_value = "error-message"

        with (
            patch("src.main.secret_manager", mock_secret_manager),
            patch("src.main.alerts_client") as mock_alerts,
        ):
            result = handler({}, MagicMock())

        assert result.startswith("Error getting access token:")
        assert any("Error getting access token" in record.getMessage() for record in caplog.records)
        mock_alerts.post_to_webhook.assert_called_once()


class TestGetAndUpdateHistoricUsage:
    def setup_method(self):
        self.org_patch = patch("src.main.org", "test-org")
        self.org_patch.start()

    def teardown_method(self):
        self.org_patch.stop()

    def test_get_and_update_historic_usage_success(self):
        s3 = MagicMock()
        gh = MagicMock()

        gh.get.return_value.json.return_value = api_response

        # Mock S3 get_object returns existing historic usage with one date
        existing_usage = [{"day": "2024-01-01", "usage": 10}]
        s3.get_object.return_value = {"Body": BytesIO(json.dumps(existing_usage).encode("utf-8"))}

        # Mock requests.get returns usage data from download_links
        # We always patch dependencies imported inside the function we're testing.
        # Test environment initialisation ends here.
        with patch("src.main.get") as mock_get:
            mock_get.return_value.json.return_value = fetched_usage_data
            result, dates_added = get_and_update_historic_usage(s3, gh, False)

        assert result == [
            {"day": "2024-01-01", "usage": 10},
            {"day": "2024-01-02", "usage": 20},
        ]
        assert dates_added == ["2024-01-02"]
        s3.get_object.assert_called_once()
        s3.put_object.assert_called_once()
        args, kwargs = s3.put_object.call_args
        assert kwargs["Bucket"].endswith("copilot-usage-dashboard")
        assert kwargs["Key"] == "organisation_history.json"
        assert json.loads(kwargs["Body"].decode("utf-8")) == result

    def test_get_and_update_historic_usage_no_existing_data(self, caplog):
        s3 = MagicMock()
        gh = MagicMock()

        gh.get.return_value.json.return_value = api_response

        # S3 get_object raises ClientError
        s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "404", "Message": "Not Found"}},
            operation_name="GetObject",
        )

        with patch("src.main.get") as mock_get:
            mock_get.return_value.json.return_value = fetched_usage_data
            result, dates_added = get_and_update_historic_usage(s3, gh, False)

        assert result == [{"day": "2024-01-01", "usage": 10}, {"day": "2024-01-02", "usage": 20}]
        assert dates_added == ["2024-01-01", "2024-01-02"]
        s3.put_object.assert_called_once()
        assert any(
            "Error getting organisation_history.json" in record.getMessage()
            for record in caplog.records
        )

    def test_get_and_update_historic_usage_api_error(self):
        s3 = MagicMock()
        gh = MagicMock()
        gh.get.return_value.json.side_effect = AttributeError("API unavailable")

        with patch("src.main.alerts_client") as mock_alerts:
            result, dates_added = get_and_update_historic_usage(s3, gh, False)

        assert result == []
        assert dates_added == []
        s3.get_object.assert_not_called()
        mock_alerts.post_to_webhook.assert_called_once()

    def test_get_and_update_historic_usage_no_new_dates(self):
        s3 = MagicMock()
        gh = MagicMock()

        gh.get.return_value.json.return_value = api_response

        # S3 get_object returns same date as usage_data
        existing_usage = [{"day": "2024-01-01", "usage": 10}, {"day": "2024-01-02", "usage": 20}]
        s3.get_object.return_value = {"Body": BytesIO(json.dumps(existing_usage).encode("utf-8"))}
        with patch("src.main.get") as mock_get:
            mock_get.return_value.json.return_value = fetched_usage_data
            result, dates_added = get_and_update_historic_usage(s3, gh, False)

        assert result == [{"day": "2024-01-01", "usage": 10}, {"day": "2024-01-02", "usage": 20}]
        assert dates_added == []
        s3.put_object.assert_called_once()

    def test_write_data_locally_creates_file(self, tmp_path):
        s3 = MagicMock()
        gh = MagicMock()

        gh.get.return_value.json.return_value = api_response

        # S3 get_object raises ClientError
        s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "404", "Message": "Not Found"}},
            operation_name="GetObject",
        )

        # Patch os.makedirs and open to use tmp_path
        with (
            patch("src.main.os.makedirs") as mock_makedirs,
            patch("src.main.open", create=True) as mock_open,
            patch("src.main.get") as mock_get,
        ):
            mock_get.return_value.json.return_value = fetched_usage_data
            result, dates_added = get_and_update_historic_usage(s3, gh, True)
            assert result == [
                {"day": "2024-01-01", "usage": 10},
                {"day": "2024-01-02", "usage": 20},
            ]
            assert dates_added == ["2024-01-01", "2024-01-02"]
            mock_makedirs.assert_called_once_with("output", exist_ok=True)
            mock_open.assert_called_once()
            s3.put_object.assert_not_called()


class TestGetDictValue:
    def test_get_dict_value_returns_value(self):
        d = {"foo": "bar", "baz": 42}
        assert get_dict_value(d, "foo") == "bar"
        assert get_dict_value(d, "baz") == 42

    def test_get_dict_value_raises_for_missing_key(self):
        d = {"foo": "bar"}
        try:
            get_dict_value(d, "missing")
        except ValueError as e:
            assert str(e) == "Key missing not found in the dictionary."
        else:
            assert False, "ValueError not raised for missing key"

    def test_get_dict_value_returns_none_for_key_with_none_value(self):
        d = {"foo": None}
        try:
            get_dict_value(d, "foo")
        except ValueError as e:
            assert str(e) == "Key foo not found in the dictionary."
        else:
            assert False, "ValueError not raised for None value"


class TestGetConfigFile:
    def test_get_config_file_success(self, tmp_path):
        config_data = {"features": {"show_log_locally": False}}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        result = get_config_file(str(config_path))
        assert result == config_data

    def test_get_config_file_file_not_found(self):
        missing_path = "nonexistent_config.json"
        try:
            get_config_file(missing_path)
        except FileNotFoundError as e:
            assert missing_path in str(e)
        else:
            assert False, "FileNotFoundError not raised"

    def test_get_config_file_not_dict(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        try:
            get_config_file(str(config_path))
        except TypeError as e:
            assert "is not a dictionary" in str(e)
        else:
            assert False, "TypeError not raised for non-dict config"


class TestAlertConfiguration:
    def test_import_requires_alert_secret_name(self):
        with patch.dict(os.environ, {"ALERT_SECRET_NAME": ""}):
            with pytest.raises(ValueError, match="ALERT_SECRET_NAME"):
                reload_main_with_alert_secret(json.dumps(alert_secret_values))

        reload_main_with_alert_secret(json.dumps(alert_secret_values))

    def test_import_requires_alert_secret_keys(self):
        with pytest.raises(ValueError, match="Missing required alert secret key"):
            reload_main_with_alert_secret(json.dumps({}))

        reload_main_with_alert_secret(json.dumps(alert_secret_values))
