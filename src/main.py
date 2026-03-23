"""GitHub Copilot Usage Lambda.

This module contains the AWS Lambda handler and supporting functions for
gathering, storing, and updating GitHub Copilot usage metrics and team history
for an organization. Data is retrieved from the GitHub API and stored in S3.
"""

import json
import logging
import os
from typing import Any

import boto3
import github_api_toolkit
from botocore.exceptions import ClientError
from requests import get

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
OBJECT_NAME = "organisation_history.json"

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


def get_and_update_historic_usage(
    s3: boto3.client, gh: github_api_toolkit.github_interface, write_data_locally: bool
) -> tuple:
    """Get and update historic usage data from GitHub Copilot.

    Args:
        s3 (boto3.client): An S3 client.
        gh (github_api_toolkit.github_interface): An instance of the github_interface class.
        write_data_locally (bool): Whether to write data locally instead of to an S3 bucket.

    Returns:
        tuple: A tuple containing the updated historic usage data and a list of dates added.
    """
    # Get the usage data
    try:
        api_response = gh.get(f"/orgs/{org}/copilot/metrics/reports/organization-28-day/latest")
        api_response_json = api_response.json()
    except AttributeError:
        logger.error("Error getting usage data: %s", api_response)
        return [], []

    usage_data = get(api_response_json["download_links"][0], timeout=30).json()["day_totals"]
    logger.info("Usage data retrieved")

    # Get the existing historic usage data from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_NAME)
        historic_usage = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        logger.error("Error getting %s: %s. Using empty list.", OBJECT_NAME, e)
        historic_usage = []

    # Append the new usage data to the existing historic usage data
    dates_added = []
    new_usage_data = []
    historic_usage_set = {d["day"] for d in historic_usage}

    for day in usage_data:
        if day["day"] not in historic_usage_set:
            new_usage_data.append(day)
            dates_added.append(day["day"])
            logger.info("Added data for day %s", day["day"])

    historic_usage.extend(sorted(new_usage_data, key=lambda x: x["day"]))

    if not write_data_locally:
        # Write the updated historic_usage to organisation_history.json
        update_s3_object(s3, BUCKET_NAME, OBJECT_NAME, historic_usage)
    else:
        local_path = f"output/{OBJECT_NAME}"
        os.makedirs("output", exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(historic_usage, f, indent=4)
        logger.info("Historic usage data written locally to %s (S3 skipped)", local_path)

    logger.info(
        "Usage data written to %s: %d days added (%s)",
        OBJECT_NAME,
        len(dates_added),
        dates_added,
    )

    return historic_usage, dates_added


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
        raise ValueError(f"Key {key} not found in the dictionary.")

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
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        error_message = f"{path} configuration file not found. Please check the path."
        raise FileNotFoundError(error_message) from None

    if not isinstance(config, dict):
        error_message = (
            f"{path} configuration file is not a dictionary. Please check the file contents."
        )
        raise TypeError(error_message)

    return config


def handler(event: dict, context) -> str:  # pylint: disable=unused-argument, too-many-locals
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

    show_logs_in_terminal = get_dict_value(features, "show_logs_in_terminal")

    write_data_locally = get_dict_value(features, "write_data_locally")

    # Toggle local logging
    if show_logs_in_terminal:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

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

    logger.info(
        "Process finished",
        extra={
            "bucket": BUCKET_NAME,
            "no_days_added": len(dates_added),
            "dates_added": dates_added,
            "no_dates_before": len(historic_usage) - len(dates_added),
            "no_dates_after": len(historic_usage),
        },
    )

    return "Github Data logging is now complete."


# Dev Only
# Uncomment the following line to run the script locally
if __name__ == "__main__":
    handler(None, None)
