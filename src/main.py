"""GitHub Copilot Usage Lambda.

This module contains the AWS Lambda handler and supporting functions for
gathering, storing, and updating GitHub Copilot usage metrics and team history
for an organization. Data is retrieved from the GitHub API and stored in S3.
"""

import json
import logging
import os
from typing import Any, Optional

import boto3
import github_api_toolkit
from botocore.exceptions import ClientError
from requests import Response

# GitHub Organisation
org = os.getenv("GITHUB_ORG")

# GitHub App Client ID
client_id = os.getenv("GITHUB_APP_CLIENT_ID")

# AWS Secret Manager Secret Name for the .pem file
secret_name = os.getenv("AWS_SECRET_NAME")
secret_region = os.getenv("AWS_DEFAULT_REGION")

account = os.getenv("AWS_ACCOUNT_NAME")

# AWS Bucket Path
BUCKET_NAME = f"{account}-copilot-usage-dashboard"
OBJECT_NAME = "historic_usage_data.json"

logger = logging.getLogger()

logger.setLevel(logging.INFO)

# Example Log Output:
#
# Standard output:
# {
#     "timestamp":"2023-10-27T19:17:45.586Z",
#     "level":"INFO",
#     "message":"Inside the handler function",
#     "logger": "root",
#     "requestId":"79b4f56e-95b1-4643-9700-2807f4e68189"
# }
#
# Output with extra fields:
# {
#     "timestamp":"2023-10-27T19:17:45.586Z",
#     "level":"INFO",
#     "message":"Inside the handler function",
#     "logger": "root",
#     "requestId":"79b4f56e-95b1-4643-9700-2807f4e68189",
#     "records_added": 10
# }


def get_copilot_team_date(gh: github_api_toolkit.github_interface, page: int) -> list:
    """Gets a list of GitHub Teams with Copilot Data for a given API page.

    Args:
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        page (int): The page number of the API request.

    Returns:
        list: A list of GitHub Teams with Copilot Data.
    """
    copilot_teams = []

    response = gh.get(f"/orgs/{org}/teams", params={"per_page": 100, "page": page})
    teams = response.json()
    for team in teams:
        usage_data = gh.get(f"/orgs/{org}/team/{team['name']}/copilot/metrics")

        if not isinstance(usage_data, Response):

            # If the response is not a Response object, no copilot data is available for this team
            # We can then skip this team

            # We don't log this as an error, as it is expected and it'd be too noisy within logs

            continue

        # If the response has data, append the team to the list
        # If there is no data, .json() will return an empty list
        if usage_data.json():

            team_name = team.get("name", "")
            team_slug = team.get("slug", "")
            team_description = team.get("description", "")
            team_html_url = team.get("html_url", "")

            logger.info(
                "Team %s has Copilot data",
                extra={
                    "team_name": team_name,
                    "team_slug": team_slug,
                    "team_description": team_description,
                    "team_html_url": team_html_url,
                },
            )

            copilot_teams.append(
                {
                    "name": team_name,
                    "slug": team_slug,
                    "description": team_description,
                    "url": team_html_url,
                }
            )

    return copilot_teams


def get_and_update_historic_usage(
    s3: boto3.client, gh: github_api_toolkit.github_interface, write_data_locally: bool
) -> tuple:
    """Get and update historic usage data from GitHub Copilot.

    Args:
        s3 (boto3.client): An S3 client.
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        write_data_locally (bool): Whether to write data locally instead of to S3.

    Returns:
        tuple: A tuple containing the updated historic usage data and a list of dates added.
    """
    # Get the usage data
    usage_data = gh.get(f"/orgs/{org}/copilot/metrics")
    usage_data = usage_data.json()

    logger.info("Usage data retrieved")

    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_NAME)
        historic_usage = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        logger.error("Error getting %s: %s. Using empty list.", OBJECT_NAME, e)

        historic_usage = []

    dates_added = []

    # Append the new usage data to the historic_usage_data.json
    for date in usage_data:
        if not any(d["date"] == date["date"] for d in historic_usage):
            historic_usage.append(date)

            dates_added.append(date["date"])

    logger.info(
        "New usage data added to %s",
        OBJECT_NAME,
        extra={"no_days_added": len(dates_added), "dates_added": dates_added},
    )

    if not write_data_locally:
        # Write the updated historic_usage to historic_usage_data.json
        update_s3_object(s3, BUCKET_NAME, OBJECT_NAME, historic_usage)
    else:
        local_path = f"local_data/{OBJECT_NAME}"
        os.makedirs("local_data", exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(historic_usage, f, indent=4)
        logger.info("Historic usage data written locally to %s (S3 skipped)", local_path)

    return historic_usage, dates_added


def get_and_update_copilot_teams(
    s3: boto3.client, gh: github_api_toolkit.github_interface, write_data_locally: bool
) -> list:
    """Get and update GitHub Teams with Copilot Data.

    Args:
        s3 (boto3.client): An S3 client.
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        write_data_locally (bool): Whether to write data locally instead of to S3.

    Returns:
        list: A list of GitHub Teams with Copilot Data.
    """
    logger.info("Getting GitHub Teams with Copilot Data")

    copilot_teams = []

    response = gh.get(f"/orgs/{org}/teams", params={"per_page": 100})

    # Get the last page of teams
    try:
        last_page = int(response.links["last"]["url"].split("=")[-1])
    except KeyError:
        last_page = 1

    for page in range(1, last_page + 1):
        page_teams = get_copilot_team_date(gh, page)

        copilot_teams = copilot_teams + page_teams

    logger.info(
        "Fetched GitHub Teams with Copilot Data",
        extra={"no_teams": len(copilot_teams)},
    )

    if not write_data_locally:
        update_s3_object(s3, BUCKET_NAME, "copilot_teams.json", copilot_teams)
    else:
        local_path = "local_data/copilot_teams.json"
        os.makedirs("local_data", exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(copilot_teams, f, indent=4)
        logger.info("Copilot teams data written locally to %s (S3 skipped)", local_path)

    return copilot_teams


def create_dictionary(
    gh: github_api_toolkit.github_interface, copilot_teams: list, existing_team_history: list
) -> list:
    """Create a dictionary for quick lookup of existing team data using the `name` field.

    Args:
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        copilot_teams (list): List of teams with Copilot data.
        existing_team_history (list): List of existing team history data.

    Returns:
        list: A list of dictionaries containing team data and their history.
    """
    existing_team_data_map = {
        single_team["team"]["name"]: single_team for single_team in existing_team_history
    }

    # Iterate through identified teams
    for team in copilot_teams:
        team_name = team.get("name", "")
        if not team_name:
            logger.warning("Skipping team with no name")
            continue

        # Determine the last known date for the team
        last_known_date = None
        if team_name in existing_team_data_map:
            existing_dates = [entry["date"] for entry in existing_team_data_map[team_name]["data"]]
            if existing_dates:
                last_known_date = max(existing_dates)  # Get the most recent date

        # Assign the last known date to the `since` query parameter
        query_params = {}
        if last_known_date:
            query_params["since"] = last_known_date

        single_team_history = get_team_history(gh, team_name, query_params)
        if not single_team_history:
            logger.info("No new history found for team %s", team_name)
            continue

        # Append new data to the existing team history
        new_team_data = single_team_history
        if team_name in existing_team_data_map:
            existing_team_data_map[team_name]["data"].extend(new_team_data)
        else:
            existing_team_data_map[team_name] = {"team": team, "data": new_team_data}

    return list(existing_team_data_map.values())


def update_s3_object(
    s3_client: boto3.client,
    bucket_name: str,
    object_name: str,
    data: dict,
) -> bool:
    """Update an S3 object with new data.

    Args:
        s3_client (boto3.client): The S3 client.
        bucket_name (str): The name of the S3 bucket.
        object_name (str): The name of the S3 object.
        data (dict): The data to be written to the S3 object.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=json.dumps(data, indent=4).encode("utf-8"),
        )
        logger.info("Successfully updated %s in bucket %s", object_name, bucket_name)
        return True
    except ClientError as e:
        logger.error("Failed to update %s in bucket %s: %s", object_name, bucket_name, e)
        return False


def get_team_history(
    gh: github_api_toolkit.github_interface, team: str, query_params: Optional[dict] = None
) -> list[dict]:
    """Gets the team metrics Copilot data through the API.
    Note - This endpoint will only return results for a given day if the team had
    five or more members with active Copilot licenses on that day,
    as evaluated at the end of that day.

    Args:
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        team (str): Team name.
        query_params (dict): Additional query parameters for the API request.

    Returns:
        list[dict]: A team's GitHub Copilot metrics or None if an error occurs.
    """
    response = gh.get(f"/orgs/{org}/team/{team}/copilot/metrics", params=query_params)

    if not isinstance(response, Response):
        logger.error("Unexpected response type: %s", type(response))
        return None
    return response.json()


def get_dict_value(dictionary: dict, key: str) -> Any:
    """Gets a value from a dictionary and raises an exception if it is not found.

    Args:
        dictionary (dict): The dictionary to get the value from.
        key (str): The key to get the value for.

    Raises:
        Exception: If the key is not found in the dictionary.

    Returns:
        Any: The value of the key in the dictionary.
    """
    value = dictionary.get(key)

    if value is None:
        raise Exception(f"Key {key} not found in the dictionary.")

    return value


def get_config_file(path: str) -> Any:
    """Loads a configuration file as a dictionary.

    Args:
        path (str): The path to the configuration file.

    Raises:
        Exception: If the configuration file is not found.

    Returns:
        Any: The configuration file as a dictionary.
    """
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        error_message = f"{path} configuration file not found. Please check the path."
        raise Exception(error_message) from None

    if type(config) is not dict:
        error_message = (
            f"{path} configuration file is not a dictionary. Please check the file contents."
        )
        raise Exception(error_message)

    return config


def handler(event: dict, context) -> str:  # pylint: disable=unused-argument
    """AWS Lambda handler function for GitHub Copilot usage data aggregation.

    This function:
    - Retrieves Copilot usage data from the GitHub API.
    - Appends new usage data to historical data stored in S3.
    - Retrieves and stores GitHub teams with Copilot usage.
    - Updates team history data in S3.
    - Logs progress and errors.

    Args:
        event (dict): AWS Lambda event payload.
        context (LambdaContext): AWS Lambda context object.

    Returns:
        str: Completion message.
    """
    # Load config file
    config = get_config_file("./config/config.json")

    features = get_dict_value(config, "features")

    show_log_locally = get_dict_value(features, "show_log_locally")

    write_data_locally = get_dict_value(features, "write_data_locally")

    # Remove any existing handlers to avoid duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()

    # Toggle local logging
    if show_log_locally:
        # Add a StreamHandler to log to the console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Create an S3 client
    session = boto3.Session()
    s3 = session.client("s3")

    logger.info("S3 client created")

    # Get the .pem file from AWS Secrets Manager
    secret_manager = session.client("secretsmanager", region_name=secret_region)

    logger.info("Secret Manager client created")

    secret = secret_manager.get_secret_value(SecretId=secret_name)["SecretString"]

    # Get updated copilot usage data from GitHub API
    access_token = github_api_toolkit.get_token_as_installation(org, secret, client_id)

    if isinstance(access_token, str):
        logger.error("Error getting access token: %s", access_token)
        return f"Error getting access token: {access_token}"
    logger.info("Access token retrieved using AWS Secret")

    # Create an instance of the api_controller class
    gh = github_api_toolkit.github_interface(access_token[0])

    logger.info("API Controller created")

    # Copilot Usage Data (Historic)
    historic_usage, dates_added = get_and_update_historic_usage(s3, gh, write_data_locally)

    # GitHub Teams with Copilot Data
    copilot_teams = get_and_update_copilot_teams(s3, gh, write_data_locally)

    logger.info("Getting history of each team identified previously")

    # Retrieve existing team history from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key="teams_history.json")
        existing_team_history = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        logger.warning("Error retrieving existing team history: %s", e)
        existing_team_history = []

    logger.info("Existing team history has %d entries", len(existing_team_history))

    if not write_data_locally:
        # Convert to dictionary for quick lookup
        updated_team_history = create_dictionary(gh, copilot_teams, existing_team_history)

        # Write updated team history to S3
        update_s3_object(s3, BUCKET_NAME, "teams_history.json", updated_team_history)
    else:
        local_path = "local_data/teams_history.json"
        os.makedirs("local_data", exist_ok=True)
        updated_team_history = create_dictionary(gh, copilot_teams, existing_team_history)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(updated_team_history, f, indent=4)
        logger.info("Team history written locally to %s (S3 skipped)", local_path)

    logger.info(
        "Process complete",
        extra={
            "bucket": BUCKET_NAME,
            "no_days_added": len(dates_added),
            "dates_added": dates_added,
            "no_dates_before": len(historic_usage) - len(dates_added),
            "no_dates_after": len(historic_usage),
            "no_copilot_teams": len(copilot_teams),
        },
    )

    return "Github Data logging is now complete."


# # Dev Only
# # Uncomment the following line to run the script locally
# if __name__ == "__main__":
#     handler(None, None)
