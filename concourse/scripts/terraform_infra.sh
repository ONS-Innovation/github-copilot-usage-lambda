#!/bin/sh

# shellcheck disable=SC2154,SC3040

set -euo pipefail

apk add --no-cache jq

lambda_name=$(echo "$secrets" | jq -r .lambda_name)
env_name=$(echo "$secrets" | jq -r .env_name)

lambda_timeout=$(echo "$secrets" | jq -r .lambda_timeout)

github_org=$(echo "$secrets" | jq -r .github_org)

github_client_id_secret_name=$(echo "$secrets" | jq -r .github_client_id_secret_name)
github_private_key_secret_name=$(echo "$secrets" | jq -r .github_private_key_secret_name)
alert_secret_name=$(echo "$secrets" | jq -r .alert_secret_name)

# kingfisher:ignore
git config --global url."https://x-access-token:$github_access_token@github.com/".insteadOf "https://github.com/"

if [ "${env}" != "prod" ]; then
	env="dev"
fi

echo "${env}"

cd resource-repo/terraform

terraform init -backend-config=env/"${env}"/backend-"${env}".tfbackend -reconfigure

# The following terraform-apply may need to change if the environment variables change

terraform apply \
	-var "env_name=$env_name" \
	-var "lambda_name=${lambda_name}" \
	-var "github_org=$github_org" \
	-var "github_client_id_secret_name=$github_client_id_secret_name" \
	-var "github_private_key_secret_name=$github_private_key_secret_name" \
	-var "alert_secret_name=$alert_secret_name" \
	-var "lambda_timeout=${lambda_timeout}" \
	-var "container_ver=${tag}" \
	-auto-approve
