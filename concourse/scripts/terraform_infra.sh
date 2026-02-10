#!/bin/sh

# shellcheck disable=SC2154,SC3040

set -euo pipefail

apk add --no-cache jq

aws_account_id=$(echo "$secrets" | jq -r .aws_account_id)
aws_access_key_id=$(echo "$secrets" | jq -r .aws_access_key_id)
aws_secret_access_key=$(echo "$secrets" | jq -r .aws_secret_access_key)

lambda_name=$(echo "$secrets" | jq -r .lambda_name)
env_name=$(echo "$secrets" | jq -r .env_name)

lambda_timeout=$(echo "$secrets" | jq -r .lambda_timeout)

github_app_client_id=$(echo "$secrets" | jq -r .github_app_client_id)
aws_secret_name=$(echo "$secrets" | jq -r .aws_secret_name)
github_org=$(echo "$secrets" | jq -r .github_org)

export AWS_ACCESS_KEY_ID="$aws_access_key_id"
export AWS_SECRET_ACCESS_KEY="$aws_secret_access_key"

git config --global url."https://x-access-token:$github_access_token@github.com/".insteadOf "https://github.com/"

if [ "${env}" != "prod" ]; then
	env="dev"
fi

echo "${env}"

cd resource-repo/terraform

terraform init -backend-config=env/"${env}"/backend-"${env}".tfbackend -reconfigure

# The following terraform-apply may need to change if the environment variables change

terraform apply \
	-var "aws_account_id=$aws_account_id" \
	-var "aws_access_key_id=$aws_access_key_id" \
	-var "aws_secret_access_key=$aws_secret_access_key" \
	-var "env_name=$env_name" \
	-var "lambda_name=${lambda_name}" \
	-var "github_app_client_id=$github_app_client_id" \
	-var "aws_secret_name=$aws_secret_name" \
	-var "github_org=$github_org" \
	-var "lambda_version=${tag}" \
	-var "lambda_timeout=${lambda_timeout}" \
	-auto-approve
