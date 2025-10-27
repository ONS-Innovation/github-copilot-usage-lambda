# GitHub Copilot Usage Lambda

This repository contains the AWS Lambda Function for updating the GitHub Copilot dashboard's historic information, stored within an S3 bucket.

The Copilot dashboard can be found on the Copilot tab within the Digital Landscape.

[View the Digital Landscape's repository](https://github.com/ONS-Innovation/keh-digital-landscape).

---

## Table of Contents

- [GitHub Copilot Usage Lambda](#github-copilot-usage-lambda)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Makefile](#makefile)
  - [AWS Lambda Scripts](#aws-lambda-scripts)
    - [Setup - Running in a container](#setup---running-in-a-container)
    - [Setup - running outside of a Container (Development only)](#setup---running-outside-of-a-container-development-only)
    - [Storing the container on AWS Elastic Container Registry (ECR)](#storing-the-container-on-aws-elastic-container-registry-ecr)
    - [Deployment to AWS](#deployment-to-aws)
      - [Deployment Prerequisites](#deployment-prerequisites)
        - [Underlying AWS Infrastructure](#underlying-aws-infrastructure)
        - [Bootstrap IAM User Groups, Users and an ECSTaskExecutionRole](#bootstrap-iam-user-groups-users-and-an-ecstaskexecutionrole)
        - [Bootstrap for Terraform](#bootstrap-for-terraform)
        - [Running the Terraform](#running-the-terraform)
      - [Updating the running service using Terraform](#updating-the-running-service-using-terraform)
      - [Destroy the Main Service Resources](#destroy-the-main-service-resources)
  - [Deployments with Concourse](#deployments-with-concourse)
    - [Allowlisting your IP](#allowlisting-your-ip)
    - [Setting up a pipeline](#setting-up-a-pipeline)
    - [Triggering a pipeline](#triggering-a-pipeline)
  - [Documentation](#documentation)
  - [Testing](#testing)
  - [Linting](#linting)
    - [Python](#python)
    - [Markdown](#markdown)
      - [Markdown Configuration](#markdown-configuration)
      - [Markdown GitHub Action](#markdown-github-action)
    - [Megalinter](#megalinter)
      - [Megalinter Configuration](#megalinter-configuration)
      - [Megalinter GitHub Action](#megalinter-github-action)

## Prerequisites

- A Docker Daemon (Colima is recommended)
  - [Colima](https://github.com/abiosoft/colima)
- Terraform (For deployment)
  - [Terraform](https://www.terraform.io/)
- Poetry (For package management)
  - [Poetry](https://python-poetry.org/docs/)
- Python >3.12
  - [Python](https://www.python.org/)
- Make
  - [GNU make](https://www.gnu.org/software/make/manual/make.html#Overview)

## Makefile

This repository has a Makefile for executing common commands. To view all commands, execute `make all`.

```bash
make all
```

## AWS Lambda Scripts

This script:

1. Collects Copilot usage data from the GitHub API and appends it to the old data in S3, creating a record of historical data to show trends over time
2. Collects a list of GitHub Teams with Copilot usage data, to reduce load times in the frontend
3. Is triggered weekly via AWS EventBridge

Further information can be found in [this project's documentation](/docs/index.md).

### Setup - Running in a container

1. Build a Docker Image

   ```bash
   docker build -t copilot-usage-lambda-script .
   ```

2. Check the image exists

   ```bash
   docker images
   ```

   **Example Output:**

   | REPOSITORY                  | TAG    | IMAGE ID     | CREATED        | SIZE  |
   |-----------------------------|--------|--------------|----------------|-------|
   | copilot-usage-lambda-script | latest | 0bbe73d9256f | 11 seconds ago | 224MB |

3. Run the image locally mapping local host port (9000) to container port (8080) and passing in AWS credentials to download a .pem file from the AWS Secrets Manager to the running container. These credentials will also be used to upload and download `historic_usage_data.json` to and from S3.

   The credentials used in the below command are for a user in AWS that has permissions to retrieve secrets from AWS Secrets Manager and upload and download files from AWS S3.

   ```bash
   docker run --platform linux/amd64 -p 9000:8080 \
   -e AWS_ACCESS_KEY_ID=<aws_access_key_id> \
   -e AWS_SECRET_ACCESS_KEY=<aws_secret_access_key_id> \
   -e AWS_DEFAULT_REGION=eu-west-2 \
   -e AWS_SECRET_NAME=<aws_secret_name> \
   -e GITHUB_ORG=ONSDigital \
   -e GITHUB_APP_CLIENT_ID=<github_app_client_id> \
   -e AWS_ACCOUNT_NAME=<sdp-dev/sdp-prod> \
   copilot-usage-lambda-script
   ```

   Once the container is running, a local endpoint is created at `localhost:9000/2015-03-31/functions/function/invocations`.

4. Post to the endpoint to trigger the function

   ```bash
   curl "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
   ```

   This should return a message if successful.

5. Once testing is finished, stop the running container

   To check the container is running

   ```bash
   docker ps
   ```

   **Example output:**

   | CONTAINER ID | IMAGE                       | COMMAND                | CREATED        | STATUS        | PORTS                                     | NAMES        |
   |--------------|-----------------------------|------------------------|----------------|---------------|-------------------------------------------|--------------|
   | 3f7d64676b1a | copilot-usage-lambda-script | "/lambda-entrypoint.…" | 44 seconds ago | Up 44 seconds | 0.0.0.0:9000->8080/tcp, :::9000->8080/tcp | nice_ritchie |

   Stop the container

   ```bash
   docker stop 3f7d64676b1a
   ```

### Setup - running outside of a Container (Development only)

To run the Lambda function outside of a container, we need to execute the `handler()` function.

1. Uncomment the following at the bottom of `main.py`.

   ```python
   ...
   # if __name__ == "__main__":
   #     handler(None, None)
   ...
   ```

   **Please Note:** If uncommenting the above in `main.py`, make sure you re-comment the code _before_ pushing back to GitHub.

2. Export the required environment variables:

   ```bash
   export AWS_ACCESS_KEY_ID=<aws_access_key_id>
   export AWS_SECRET_ACCESS_KEY=<aws_secret_access_key>
   export AWS_DEFAULT_REGION=eu-west-2
   export AWS_SECRET_NAME=<aws_secret_name>
   export GITHUB_ORG=ONSDigital
   export GITHUB_APP_CLIENT_ID=<github_app_client_id>
   export AWS_ACCOUNT_NAME=<sdp-dev/sdp-prod>
   ```

3. Run the script.

   ```bash
   python3 src/main.py
   ```

### Storing the container on AWS Elastic Container Registry (ECR)

When you make changes to the Lambda Script, a new container image must be pushed to ECR.

These instructions assume:

1. You have a repository set up in your AWS account named copilot-usage-lambda-script.
2. You have created an AWS IAM user with permissions to read/write to ECR (e.g AmazonEC2ContainerRegistryFullAccess policy) and that you have created the necessary access keys for this user. The credentials for this user are stored in `~/.aws/credentials` and can be used by accessing `--profile <aws-credentials-profile\>`. If these are the only credentials in your file, the profile name is _default_

You can find the AWS repo push commands under your repository in ECR by selecting the "View Push Commands" button. This will display a guide to the following (replace `<aws-credentials-profile\>`, `<aws-account-id\>` and `<version\>` accordingly):

1. Get an authentication token and authenticate your docker client for pushing images to ECR:

   ```bash
   aws ecr --profile <aws-credentials-profile> get-login-password --region eu-west-2 | docker login --username AWS --password-stdin <aws-account-id>.dkr.ecr.eu-west-2.amazonaws.com
   ```

2. Tag your latest built docker image for ECR (assumes you have run `docker build -t sdp-repo-archive .` locally first)

   ```bash
   docker tag copilot-usage-lambda-script:latest <aws-account-id>.dkr.ecr.eu-west-2.amazonaws.com/copilot-usage-lambda-script:<version>
   ```

   **Note:** To find the `<version\>` to build, look at the latest tagged version in ECR and increment appropriately

3. Push the version up to ECR

   ```bash
   docker push <aws-account-id>.dkr.ecr.eu-west-2.amazonaws.com/copilot-usage-lambda-script:<version>
   ```

### Deployment to AWS

The deployment of the service is defined in Infrastructure as Code (IaC) using Terraform. The service is deployed as a container on an AWS Fargate Service Cluster.

#### Deployment Prerequisites

When first deploying the service to AWS, the following prerequisites are expected to be in place or added.

##### Underlying AWS Infrastructure

The Terraform in this repository expects that underlying AWS infrastructure is present in AWS to deploy on top of, i.e:

- Route53 DNS Records
- Web Application Firewall and appropriate Rules and Rule Groups
- Virtual Private Cloud with Private and Public Subnets
- Security Groups
- Application Load Balancer
- ECS Service Cluster

That infrastructure is defined in the repository [sdp-infrastructure](https://github.com/ONS-Innovation/sdp-infrastructure)

##### Bootstrap IAM User Groups, Users and an ECSTaskExecutionRole

The following users must be provisioned in AWS IAM:

- `ecr-user`
  - Used for interaction with the Elastic Container Registry from AWS cli
- `terraform-user`
  - Used for terraform staging of the resources required to deploy the service

The following groups and permissions must be defined and applied to the above users:

- `ecr-user-group`
  - EC2 Container Registry Access
- `terraform-user-group`
  - Dynamo DB Access
  - EC2 Access
  - ECS Access
  - ECS Task Execution Role Policy
  - Route53 Access
  - S3 Access
  - Cloudwatch Logs All Access (Custom Policy)
  - IAM Access
  - Secrets Manager Access

**The Lambda Script Terraform requires some additional permissions to those above:**

- `AmazonEC2ContainerRegistryFullAccess`
- `AmazonEventBridgeFullAccess`
- `AWSLambda_FullAccess`

Further to the above, an IAM Role must be defined to allow ECS tasks to be executed:

- `ecsTaskExecutionRole`
  - See the [AWS guide to create the task execution role policy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)

##### Bootstrap for Terraform

To store the state and implement a state locking mechanism for the service resources, a Terraform backend is deployed in AWS (an S3 object and DynamoDbTable).

##### Running the Terraform

- `terraform/main.tf`
  - This provisions the resources required to launch the Copilot Dashboard's data collection Lambda script (data logger).

Depending upon which environment you are deploying to, you will want to run your Terraform by pointing at an appropriate environment `tfvars` file.

Example service tfvars file:
[/env/dev/example_tfvars.txt](/terraform/env/dev/example_tfvars.txt)

#### Updating the running service using Terraform

If the application has been modified, the following can be performed to update the running service:

- Build a new version of the container image and upload to ECR as per the instructions earlier in this guide.
- Change directory to `terraform`

  ```bash
  cd terraform
  ```

- In the appropriate environment variable file `env/dev/dev.tfvars` or `env/prod/prod.tfvars`
  - Fill out the appropriate variables

- Initialise Terraform for the appropriate environment config file `backend-dev.tfbackend` or `backend-prod.tfbackend` run:

  ```bash
  terraform init -backend-config=env/dev/backend-dev.tfbackend -reconfigure
  ```

  The reconfigure options ensures that the backend state is reconfigured to point to the appropriate S3 bucket.

  **_Please Note:_** This step requires an **AWS_ACCESS_KEY_ID** and **AWS_SECRET_ACCESS_KEY** to be loaded into the environment if not already in place.
  This can be done using:

  ```bash
  export AWS_ACCESS_KEY_ID="<aws_access_key_id>"
  export AWS_SECRET_ACCESS_KEY="<aws_secret_access_key>"
  ```

- Refresh the local state to ensure it is in sync with the backend

  ```bash
  terraform refresh -var-file=env/dev/dev.tfvars
  ```

- Plan the changes, ensuring you use the correct environment config (depending upon which env you are configuring):

  E.g. for the dev environment run

  ```bash
  terraform plan -var-file=env/dev/dev.tfvars
  ```

- Apply the changes, ensuring you use the correct environment config (depending upon which env you are configuring):

  E.g. for the dev environment run

  ```bash
  terraform apply -var-file=env/dev/dev.tfvars
  ```

- When the Terraform has applied successfully, the Lambda and EventBridge Schedule will be created.

#### Destroy the Main Service Resources

Delete the service resources by running the following ensuring your reference the correct environment files for the backend-config and var files:

```bash
cd terraform

terraform init -backend-config=env/dev/backend-dev.tfbackend -reconfigure

terraform refresh -var-file=env/dev/dev.tfvars

terraform destroy -var-file=env/dev/dev.tfvars
```

## Deployments with Concourse

### Allowlisting your IP

To setup the deployment pipeline with concourse, you must first allowlist your IP address on the Concourse
server. IP addresses are flushed everyday at 00:00 so this must be done at the beginning of every working day whenever the deployment pipeline needs to be used.

Follow the instructions on the Confluence page (SDP Homepage > SDP Concourse > Concourse Login) to
login. All our pipelines run on `sdp-pipeline-prod`, whereas `sdp-pipeline-dev` is the account used for
changes to Concourse instance itself. Make sure to export all necessary environment variables from `sdp-pipeline-prod` (**AWS_ACCESS_KEY_ID**, **AWS_SECRET_ACCESS_KEY**, **AWS_SESSION_TOKEN**).

### Setting up a pipeline

When setting up our pipelines, we use `ecs-infra-user` on `sdp-dev` to be able to interact with our infrastructure on AWS. The credentials for this are stored on AWS Secrets Manager so you do not need to set up anything yourself.

To set the pipeline, run the following script:

```bash
chmod u+x ./concourse/scripts/set_pipeline.sh
./concourse/scripts/set_pipeline.sh github-copilot-usage-lambda
```

Note that you only have to run chmod the first time running the script in order to give permissions.
This script will set the branch and pipeline name to whatever branch you are currently on. It will also set the image tag on ECR to the current commit hash at the time of setting the pipeline.

The pipeline name itself will usually follow a pattern as follows: `<repo-name>-<branch-name>`
If you wish to set a pipeline for another branch without checking out, you can run the following:

```bash
./concourse/scripts/set_pipeline.sh github-copilot-usage-lambda <branch_name>
```

If the branch you are deploying is `main`, it will trigger a deployment to the `sdp-prod` environment. To set the ECR image tag, you must draft a GitHub release pointing to the latest release of the `main` branch that has a tag in the form of `vX.Y.Z.` Drafting up a release will automatically deploy the latest version of the `main` branch with the associated release tag, but you can also manually trigger a build through the Concourse UI or the terminal prompt.

### Triggering a pipeline

Once the pipeline has been set, you can manually trigger a build on the Concourse UI, or run the following command:

```bash
fly -t aws-sdp trigger-job -j github-copilot-usage-lambda-<branch-name>/build-and-push
```

## Documentation

This project uses MkDocs for documentation which gets deployed to GitHub Pages at a repository level.

For more information about MkDocs, see the below documentation.

[Getting Started with MkDocs](https://www.mkdocs.org/getting-started/)

There is a guide to getting started on this repository's GitHub Pages site.

## Testing

This project uses Pytest for testing. The tests can be found in the `tests` folder.

To run all tests, use `make test`.

On pull request or push to the `main` branch, the tests will automatically run. The workflow will fail if any tests fail, or if test coverage is below 95%.

The related workflow can be found in `.github/workflows/ci.yml`.

## Linting

### Python

This project uses Black, Ruff, and Pylint for linting and code formatting on Python files in `src`. Configurations for each are located in `pyproject.toml`.

The following Makefile commands can be used to run linting and optionally apply fixes or run a specific linter:

```bash
black-check ## Run black for code formatting, without fixing.

black-apply ## Run black and fix code formatting.

ruff-check ## Run ruff for linting and code formatting, without fixing.

ruff-apply ## Run ruff and fix linting and code formatting.

pylint ## Run pylint for code analysis.

lint  ## Run Python linters without fixing.

lint-apply ## Run black and ruff with auto-fix, and Pylint.
```

On pull request or push to the `main` branch, `make lint-check` will automatically run to check code quality, failing if there are any issues. It is up to the developer to apply fixes.

The related workflow can be found in `.github/workflows/ci.yml`.

### Markdown

Markdown linting runs in a docker image, so docker must be running before attempting to lint.

To lint all markdown files, run the following command:

```bash
make md-check
```

To fix all markdown files, run the following command:

```bash
make md-apply
```

#### Markdown Configuration

The `.markdownlint.json` file in the root of the repository contains the configuration for markdownlint. This file is used to set the rules and settings for linting markdown files.

Currently, MD013 (line length) is disabled. This is because the default line length of 80 characters is too restrictive.

For a full list of rules, see [Markdownlint Rules / Aliases](https://github.com/DavidAnson/markdownlint?tab=readme-ov-file#rules--aliases)

The `.markdownlintignore` file in the root of the repository is also used to prevent markdownlint running on unnecessary files such as `venv`.

#### Markdown GitHub Action

On pull request or push to the `main` branch, `make md-check` will automatically run to check for linting errors, failing if there are any issues. It is up to the developer to apply fixes.

The related workflow can be found in `.github/workflows/ci.yml`.

### Megalinter

In addition to Python and Markdown-specific linting, this project uses Megalinter to catch all other types of linting errors across the project.

Megalinter runs in a docker image, so docker must be running before attempting to lint.

To lint with Megalinter, run:

```bash
make megalint
```

After running, Megalinter will create a folder named `megalinter-reports` containing detailed logs on linting.

#### Megalinter Configuration

The configuration file for Megalinter can be found in the root of the repository, named `.mega-linter.yml`.

#### Megalinter GitHub Action

On pull request or push to the `main` branch, Megalinter will automatically run to check project-wide linting, failing if there are any issues.

The related workflow can be found in `.github/workflows/megalinter.yml`.
