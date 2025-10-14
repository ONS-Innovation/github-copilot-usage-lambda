import json
import os
from unittest.mock import MagicMock, call, patch

from botocore.exceptions import ClientError
from requests import Response

os.environ["AWS_ACCOUNT_NAME"] = "test"
os.environ["AWS_SECRET_NAME"] = "test-secret"
os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

from src.main import (
    BUCKET_NAME,
    create_dictionary,
    get_and_update_copilot_teams,
    get_and_update_historic_usage,
    get_copilot_team_date,
    get_team_history,
    handler,
    update_s3_object,
)


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


class TestGetAndUpdateCopilotTeams:
    @patch("src.main.update_s3_object")
    def test_get_and_update_copilot_teams_single_page(self, mock_update_s3_object):
        s3 = MagicMock()
        gh = MagicMock()
        # Mock response for first page
        mock_response = MagicMock()
        mock_response.links = {}  # No 'last' link, so only one page
        gh.get.return_value = mock_response

        # Patch get_copilot_team_date to return a list of teams
        with patch(
            "src.main.get_copilot_team_date", return_value=[{"name": "team1"}]
        ) as mock_get_team_date:
            result = get_and_update_copilot_teams(s3, gh, False)
            assert result == [{"name": "team1"}]
            mock_get_team_date.assert_called_once_with(gh, 1)
            mock_update_s3_object.assert_called_once()
            args, kwargs = mock_update_s3_object.call_args
            assert args[1].endswith("copilot-usage-dashboard")
            assert args[2] == "copilot_teams.json"
            assert args[3] == [{"name": "team1"}]

    @patch("src.main.update_s3_object")
    def test_get_and_update_copilot_teams_multiple_pages(self, mock_update_s3_object):
        s3 = MagicMock()
        gh = MagicMock()
        # Mock response with 'last' link for 3 pages
        mock_response = MagicMock()
        mock_response.links = {"last": {"url": "https://api.github.com/orgs/test/teams?page=3"}}
        gh.get.return_value = mock_response

        # Patch get_copilot_team_date to return different teams per page
        with patch(
            "src.main.get_copilot_team_date",
            side_effect=[[{"name": "team1"}], [{"name": "team2"}], [{"name": "team3"}]],
        ) as mock_get_team_date:
            result = get_and_update_copilot_teams(s3, gh, False)
            assert result == [{"name": "team1"}, {"name": "team2"}, {"name": "team3"}]
            assert mock_get_team_date.call_count == 3
            mock_update_s3_object.assert_called_once()

    @patch("src.main.update_s3_object")
    def test_get_and_update_copilot_teams_no_teams(self, mock_update_s3_object):
        s3 = MagicMock()
        gh = MagicMock()
        mock_response = MagicMock()
        mock_response.links = {}
        gh.get.return_value = mock_response

        with patch("src.main.get_copilot_team_date", return_value=[]) as mock_get_team_date:
            result = get_and_update_copilot_teams(s3, gh, False)
            assert result == []
            mock_get_team_date.assert_called_once_with(gh, 1)
            mock_update_s3_object.assert_called_once()
            args, kwargs = mock_update_s3_object.call_args
            assert args[1].endswith("copilot-usage-dashboard")
            assert args[2] == "copilot_teams.json"
            assert args[3] == []


class TestGetTeamHistory:
    def setup_method(self):
        self.org_patch = patch("src.main.org", "test-org")
        self.org_patch.start()
        self.addCleanup = getattr(self, "addCleanup", lambda f: None)

    def teardown_method(self):
        self.org_patch.stop()

    def test_get_team_history_success(self):
        gh = MagicMock()
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = [{"date": "2024-01-01", "usage": 5}]
        gh.get.return_value = mock_response

        result = get_team_history(gh, "dev-team", {"since": "2024-01-01"})
        gh.get.assert_called_once_with(
            "/orgs/test-org/team/dev-team/copilot/metrics", params={"since": "2024-01-01"}
        )
        assert result == [{"date": "2024-01-01", "usage": 5}]

    def test_get_team_history_with_no_query_params(self):
        gh = MagicMock()
        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = []
        gh.get.return_value = mock_response

        result = get_team_history(gh, "dev-team")
        gh.get.assert_called_once_with("/orgs/test-org/team/dev-team/copilot/metrics", params=None)
        assert result == []


class TestHandler:
    @patch("src.main.boto3.Session")
    @patch("src.main.github_api_toolkit.get_token_as_installation")
    @patch("src.main.github_api_toolkit.github_interface")
    @patch("src.main.get_and_update_historic_usage")
    @patch("src.main.get_and_update_copilot_teams")
    @patch("src.main.create_dictionary")
    @patch("src.main.update_s3_object")
    def test_handler_success(
        self,
        mock_update_s3_object,
        mock_create_dictionary,
        mock_get_and_update_copilot_teams,
        mock_get_and_update_historic_usage,
        mock_github_interface,
        mock_get_token_as_installation,
        mock_boto3_session,
        caplog,
    ):
        # Setup mocks
        mock_s3 = MagicMock()
        mock_secret_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.client.side_effect = [mock_s3, mock_secret_manager]
        mock_boto3_session.return_value = mock_session

        mock_secret_manager.get_secret_value.return_value = {"SecretString": "pem-content"}
        mock_get_token_as_installation.return_value = ("token",)
        mock_gh = MagicMock()
        mock_github_interface.return_value = mock_gh

        mock_get_and_update_historic_usage.return_value = (["usage1", "usage2"], ["2024-01-01"])
        mock_get_and_update_copilot_teams.return_value = [{"name": "team1"}]
        mock_create_dictionary.return_value = [
            {"team": {"name": "team1"}, "data": [{"date": "2024-01-01"}]}
        ]

        secret_region = "eu-west-1"
        secret_name = "test-secret"

        # S3 get_object for teams_history.json returns existing history
        mock_s3.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(return_value=b'[{"team": {"name": "team1"}, "data": []}]')
            )
        }

        result = handler({}, MagicMock())
        assert result == "Github Data logging is now complete."
        mock_boto3_session.assert_called_once()
        mock_session.client.assert_any_call("s3")
        call("secretsmanager", region_name=secret_region) in mock_session.client.call_args_list
        mock_secret_manager.get_secret_value.assert_called_once_with(SecretId=secret_name)
        mock_get_token_as_installation.assert_called_once()
        mock_github_interface.assert_called_once()
        mock_get_and_update_historic_usage.assert_called_once()
        mock_get_and_update_copilot_teams.assert_called_once()
        mock_create_dictionary.assert_called_once()
        mock_update_s3_object.assert_called_with(
            mock_s3, BUCKET_NAME, "teams_history.json", mock_create_dictionary.return_value
        )

    @patch("src.main.boto3.Session")
    @patch("src.main.github_api_toolkit.get_token_as_installation")
    def test_handler_access_token_error(
        self, mock_get_token_as_installation, mock_boto3_session, caplog
    ):
        mock_s3 = MagicMock()
        mock_secret_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.client.side_effect = [mock_s3, mock_secret_manager]
        mock_boto3_session.return_value = mock_session
        mock_secret_manager.get_secret_value.return_value = {"SecretString": "pem-content"}
        mock_get_token_as_installation.return_value = "error-message"

        result = handler({}, MagicMock())
        assert result.startswith("Error getting access token:")
        assert any("Error getting access token" in record.getMessage() for record in caplog.records)

    @patch("src.main.boto3.Session")
    @patch("src.main.github_api_toolkit.get_token_as_installation")
    @patch("src.main.github_api_toolkit.github_interface")
    @patch("src.main.get_and_update_historic_usage")
    @patch("src.main.get_and_update_copilot_teams")
    @patch("src.main.create_dictionary")
    @patch("src.main.update_s3_object")
    def test_handler_team_history_client_error(
        self,
        mock_update_s3_object,
        mock_create_dictionary,
        mock_get_and_update_copilot_teams,
        mock_get_and_update_historic_usage,
        mock_github_interface,
        mock_get_token_as_installation,
        mock_boto3_session,
        caplog,
    ):
        mock_s3 = MagicMock()
        mock_secret_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.client.side_effect = [mock_s3, mock_secret_manager]
        mock_boto3_session.return_value = mock_session

        mock_secret_manager.get_secret_value.return_value = {"SecretString": "pem-content"}
        mock_get_token_as_installation.return_value = ("token",)
        mock_gh = MagicMock()
        mock_github_interface.return_value = mock_gh

        mock_get_and_update_historic_usage.return_value = (["usage1"], ["2024-01-01"])
        mock_get_and_update_copilot_teams.return_value = [{"name": "team1"}]
        mock_create_dictionary.return_value = [
            {"team": {"name": "team1"}, "data": [{"date": "2024-01-01"}]}
        ]

        # S3 get_object for teams_history.json raises ClientError
        mock_s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "404", "Message": "Not Found"}},
            operation_name="GetObject",
        )

        result = handler({}, MagicMock())
        assert result == "Github Data logging is now complete."
        assert any(
            "Error retrieving existing team history" in record.getMessage()
            for record in caplog.records
        )
        mock_update_s3_object.assert_called_with(
            mock_s3, BUCKET_NAME, "teams_history.json", mock_create_dictionary.return_value
        )


class TestGetCopilotTeamDate:
    @patch("src.main.org", "test-org")
    def test_get_copilot_team_date_success(self):
        gh = MagicMock()
        # Mock teams response
        teams_response = MagicMock()
        teams_response.json.return_value = [
            {"name": "team1", "slug": "slug1", "description": "desc1", "html_url": "url1"},
            {"name": "team2", "slug": "slug2", "description": "desc2", "html_url": "url2"},
        ]
        gh.get.side_effect = [
            teams_response,
            MagicMock(spec=Response),  # usage_data for team1
            MagicMock(spec=Response),  # usage_data for team2
        ]

        result = get_copilot_team_date(gh, 1)
        assert result == [
            {"name": "team1", "slug": "slug1", "description": "desc1", "url": "url1"},
            {"name": "team2", "slug": "slug2", "description": "desc2", "url": "url2"},
        ]
        gh.get.assert_any_call("/orgs/test-org/teams", params={"per_page": 100, "page": 1})
        gh.get.assert_any_call("/orgs/test-org/team/team1/copilot/metrics")
        gh.get.assert_any_call("/orgs/test-org/team/team2/copilot/metrics")

    @patch("src.main.org", "test-org")
    def test_get_copilot_team_date_unexpected_usage_response(self, caplog):
        gh = MagicMock()
        teams_response = MagicMock()
        teams_response.json.return_value = [
            {"name": "team1", "slug": "slug1", "description": "desc1", "html_url": "url1"},
        ]
        gh.get.side_effect = [
            teams_response,
            "not_a_response",  # usage_data for team1
        ]

        with caplog.at_level("ERROR"):
            result = get_copilot_team_date(gh, 1)
            assert result == []

    @patch("src.main.org", "test-org")
    def test_get_copilot_team_date_empty_teams(self):
        gh = MagicMock()
        teams_response = MagicMock()
        teams_response.json.return_value = []
        gh.get.return_value = teams_response

        result = get_copilot_team_date(gh, 1)
        assert result == []
        gh.get.assert_called_once_with("/orgs/test-org/teams", params={"per_page": 100, "page": 1})


class TestGetAndUpdateHistoricUsage:
    def setup_method(self):
        self.org_patch = patch("src.main.org", "test-org")
        self.org_patch.start()

    def teardown_method(self):
        self.org_patch.stop()

    def test_get_and_update_historic_usage_success(self):
        s3 = MagicMock()
        gh = MagicMock()
        # Mock usage data returned from GitHub API
        usage_data = [
            {"date": "2024-01-01", "usage": 10},
            {"date": "2024-01-02", "usage": 20},
        ]
        gh.get.return_value.json.return_value = usage_data

        # Mock S3 get_object returns existing historic usage with one date
        existing_usage = [{"date": "2024-01-01", "usage": 10}]
        s3.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(return_value=json.dumps(existing_usage).encode("utf-8"))
            )
        }

        result, dates_added = get_and_update_historic_usage(s3, gh, False)
        assert result == [
            {"date": "2024-01-01", "usage": 10},
            {"date": "2024-01-02", "usage": 20},
        ]
        assert dates_added == ["2024-01-02"]
        s3.get_object.assert_called_once()
        s3.put_object.assert_called_once()
        args, kwargs = s3.put_object.call_args
        assert kwargs["Bucket"].endswith("copilot-usage-dashboard")
        assert kwargs["Key"] == "historic_usage_data.json"
        assert json.loads(kwargs["Body"].decode("utf-8")) == result

    def test_get_and_update_historic_usage_no_existing_data(self, caplog):
        s3 = MagicMock()
        gh = MagicMock()
        usage_data = [{"date": "2024-01-01", "usage": 10}]
        gh.get.return_value.json.return_value = usage_data

        # S3 get_object raises ClientError
        s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "404", "Message": "Not Found"}},
            operation_name="GetObject",
        )

        result, dates_added = get_and_update_historic_usage(s3, gh, False)
        assert result == [{"date": "2024-01-01", "usage": 10}]
        assert dates_added == ["2024-01-01"]
        s3.put_object.assert_called_once()
        assert any(
            "Error getting historic_usage_data.json" in record.getMessage()
            for record in caplog.records
        )

    def test_get_and_update_historic_usage_no_new_dates(self):
        s3 = MagicMock()
        gh = MagicMock()
        usage_data = [{"date": "2024-01-01", "usage": 10}]
        gh.get.return_value.json.return_value = usage_data

        # S3 get_object returns same date as usage_data
        existing_usage = [{"date": "2024-01-01", "usage": 10}]
        s3.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(return_value=json.dumps(existing_usage).encode("utf-8"))
            )
        }

        result, dates_added = get_and_update_historic_usage(s3, gh, False)
        assert result == [{"date": "2024-01-01", "usage": 10}]
        assert dates_added == []
        s3.put_object.assert_called_once()


class TestCreateDictionary:
    def setup_method(self):
        self.org_patch = patch("src.main.org", "test-org")
        self.org_patch.start()

    def teardown_method(self):
        self.org_patch.stop()

    def test_create_dictionary_adds_new_team_history(self):
        gh = MagicMock()
        copilot_teams = [{"name": "team1"}, {"name": "team2"}]
        existing_team_history = []

        # get_team_history returns history for each team
        with patch(
            "src.main.get_team_history",
            side_effect=[
                [{"date": "2024-01-01", "usage": 5}],
                [{"date": "2024-01-02", "usage": 10}],
            ],
        ) as mock_get_team_history:
            result = create_dictionary(gh, copilot_teams, existing_team_history)
            assert len(result) == 2
            assert result[0]["team"]["name"] == "team1"
            assert result[0]["data"] == [{"date": "2024-01-01", "usage": 5}]
            assert result[1]["team"]["name"] == "team2"
            assert result[1]["data"] == [{"date": "2024-01-02", "usage": 10}]
            assert mock_get_team_history.call_count == 2

    def test_create_dictionary_extends_existing_team_history(self):
        gh = MagicMock()
        copilot_teams = [{"name": "team1"}]
        existing_team_history = [
            {"team": {"name": "team1"}, "data": [{"date": "2024-01-01", "usage": 5}]}
        ]

        # get_team_history returns new history for team1
        with patch(
            "src.main.get_team_history", return_value=[{"date": "2024-01-02", "usage": 10}]
        ) as mock_get_team_history:
            result = create_dictionary(gh, copilot_teams, existing_team_history)
            assert len(result) == 1
            assert result[0]["team"]["name"] == "team1"
            assert result[0]["data"] == [
                {"date": "2024-01-01", "usage": 5},
                {"date": "2024-01-02", "usage": 10},
            ]
            mock_get_team_history.assert_called_once()

            args, kwargs = mock_get_team_history.call_args
            assert args[0] == gh
            assert args[1] == "team1"
            assert args[2] == {"since": "2024-01-01"}

    def test_create_dictionary_skips_team_with_no_name(self, caplog):
        gh = MagicMock()
        copilot_teams = [{"slug": "slug1"}]  # No 'name'
        existing_team_history = []

        with patch("src.main.get_team_history") as mock_get_team_history:
            result = create_dictionary(gh, copilot_teams, existing_team_history)
            assert result == []
            assert mock_get_team_history.call_count == 0
            assert any(
                "Skipping team with no name" in record.getMessage() for record in caplog.records
            )

    def test_create_dictionary_no_new_history(self, caplog):
        gh = MagicMock()
        copilot_teams = [{"name": "team1"}]
        existing_team_history = []

        # get_team_history returns empty list
        with patch("src.main.get_team_history", return_value=[]) as mock_get_team_history:
            result = create_dictionary(gh, copilot_teams, existing_team_history)
            assert result == []
            assert mock_get_team_history.call_count == 1
