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
from keh_teams_alert import TeamsAlertClient
from requests import get

# GitHub Organisation
org = os.getenv("GITHUB_ORG")

# GitHub App Secrets
client_id_secret_name = os.getenv("GITHUB_CLIENT_ID_SECRET_NAME")
private_key_secret_name = os.getenv("GITHUB_PRIVATE_KEY_SECRET_NAME")

# Teams Alert Secrets
alert_secret_name = os.getenv("ALERT_SECRET_NAME")

# AWS Information
secret_region = os.getenv("AWS_DEFAULT_REGION")
account = os.getenv("AWS_ACCOUNT_NAME")

# AWS Bucket Path
BUCKET_NAME = f"{account}-copilot-usage-dashboard"
OBJECT_NAME = "organisation_history.json"

logger = logging.getLogger()

logger.setLevel(logging.INFO)

# Initialise AWS clients

session = boto3.Session()
s3 = session.client("s3")
secret_manager = session.client("secretsmanager", region_name=secret_region)

# Initialise Teams Alerts
logger.info("Initialising Teams Alerts")

if not alert_secret_name:
    raise ValueError("ALERT_SECRET_NAME environment variable is not set")

alert_secrets = secret_manager.get_secret_value(SecretId=alert_secret_name)
alert_secrets_dict = json.loads(alert_secrets["SecretString"])

# Verify required secret values are present
required_keys = [
    "azure_tenant_id",
    "azure_client_id",
    "azure_client_secret",
    "azure_webhook_url",
    "channel_id",
]
for required_key in required_keys:
    if required_key not in alert_secrets_dict:
        raise ValueError(f"Missing required alert secret key: {required_key}")

channel_id = alert_secrets_dict.get("channel_id")
azure_webhook_url = alert_secrets_dict.get("azure_webhook_url")

alerts_client = TeamsAlertClient(
    tenant_id=alert_secrets_dict.get("azure_tenant_id"),
    client_id=alert_secrets_dict.get("azure_client_id"),
    client_secret=alert_secrets_dict.get("azure_client_secret"),
    scope="https://management.azure.com/.default",
)

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
    s3_client: boto3.client,
    gh: github_api_toolkit.github_interface,
    write_data_locally: bool,
) -> tuple:
    """Get and update historic usage data from GitHub Copilot.

    Args:
        s3_client (boto3.client): An S3 client.
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

        alerts_client.post_to_webhook(
            webhook_url=azure_webhook_url,
            payload={
                "channel": channel_id,
                "message": (
                    f"<b>{account} Copilot Lambda</b><br>Error getting usage data: {api_response}"
                ),
            },
        )

        return [], []

    usage_data = get(api_response_json["download_links"][0], timeout=30).json()["day_totals"]
    logger.info("Usage data retrieved")

    # Get the existing historic usage data from S3
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=OBJECT_NAME)
        historic_usage = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        logger.error("Error getting %s: %s. Using empty list.", OBJECT_NAME, e)

        alerts_client.post_to_webhook(
            webhook_url=azure_webhook_url,
            payload={
                "channel": channel_id,
                "message": (
                    f"<b>{account} Copilot Lambda</b><br>Error getting {OBJECT_NAME} "
                    f"from S3: {e}. Using empty list."
                ),
            },
        )

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
        update_s3_object(s3_client, BUCKET_NAME, OBJECT_NAME, historic_usage)
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

        alerts_client.post_to_webhook(
            webhook_url=azure_webhook_url,
            payload={
                "channel": channel_id,
                "message": (
                    f"<b>{account} Copilot Lambda</b><br>Failed to update {object_name} "
                    f"in bucket {bucket_name}: {e}"
                ),
            },
        )

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

    write_data_locally = get_dict_value(features, "write_data_locally")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Initialise GitHub App credentials from AWS Secrets Manager
    logger.info("Initialising GitHub App credentials from AWS Secrets Manager")

    if not client_id_secret_name:
        raise ValueError("CLIENT_ID_SECRET_NAME environment variable is not set")
    if not private_key_secret_name:
        raise ValueError("PRIVATE_KEY_SECRET_NAME environment variable is not set")

    client_id = secret_manager.get_secret_value(SecretId=client_id_secret_name)["SecretString"]
    client_id = json.loads(client_id).get("ClientID")

    if not client_id:
        raise ValueError(
            "Failed to retrieve ClientID from AWS Secrets Manager. "
            "Verify that the secret contains a ClientID key."
        )

    private_key = secret_manager.get_secret_value(SecretId=private_key_secret_name)["SecretString"]

    if not private_key:
        raise ValueError("Failed to retrieve private key from AWS Secrets Manager.")

    # Get updated copilot usage data from GitHub API
    logger.info("Getting GitHub access token as installation")

    access_token = github_api_toolkit.get_token_as_installation(org, private_key, client_id)

    if isinstance(access_token, str):
        logger.error("Error getting access token: %s", access_token)

        alerts_client.post_to_webhook(
            webhook_url=azure_webhook_url,
            payload={
                "channel": channel_id,
                "message": (
                    f"<b>{account} Copilot Lambda</b><br>Error getting access token: {access_token}"
                ),
            },
        )

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

    alerts_client.post_to_webhook(
        webhook_url=azure_webhook_url,
        payload={
            "channel": channel_id,
            "message": (
                f"<b>{account} Copilot Lambda</b><br>"
                "Successfully processed GitHub Copilot usage data.<br>"
                f"No. of dates added: {len(dates_added)}<br>"
                f"Dates added: {dates_added}<br>"
                f"No. of dates before: {len(historic_usage) - len(dates_added)}<br>"
                f"No. of dates after: {len(historic_usage)}"
            ),
        },
    )

    return "Github Data logging is now complete."


# Dev Only
# Uncomment the following line to run the script locally
# if __name__ == "__main__":
#     handler(None, None)
