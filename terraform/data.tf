data "aws_ecr_repository" "profile_lambda_ecr_repo" {
  name = local.lambda_repo
}

# Get the ecs infrastructure outputs from the remote state data source
data "terraform_remote_state" "vpc" {
  backend = "s3"
  config = {
    bucket = "${var.env_name}-tf-state"
    key    = "${var.env_name}-ecs-infra/terraform.tfstate"
    region = "eu-west-2"
  }
}

data "aws_iam_policy_document" "vpc_permissions" {
  statement {
    effect = "Allow"

    actions = [
      "ec2:DescribeNetworkInterfaces",
      "ec2:CreateNetworkInterface",
      "ec2:DeleteNetworkInterface",
      "ec2:DescribeInstances",
      "ec2:AttachNetworkInterface",
      "ec2:CreateTags"
    ]

    resources = ["*"]
  }
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "${aws_cloudwatch_log_group.loggroup.arn}:*"
    ]
  }
}

data "aws_iam_policy_document" "lambda_s3_policy" {
  statement {
    effect = "Allow"

    actions = [
      "s3:ListAllMyBuckets", # Allows listing all buckets in the account
      "s3:GetObject",        # Allows reading objects in buckets
      "s3:PutObject",        # Allows writing objects to buckets
      "s3:ListBucket"
    ]

    resources = [
      "arn:aws:s3:::*",  # Allows access to all buckets
      "arn:aws:s3:::*/*" # Allows access to all objects within all buckets
    ]
  }
}

data "aws_iam_policy_document" "lambda_secret_manager_policy" {
  statement {
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      "arn:aws:secretsmanager:*:*:secret:${var.aws_secret_name}*"
    ]
  }
}

data "aws_iam_policy_document" "lambda_eventbridge_policy" {
  statement {
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction"
    ]
    resources = [
      aws_lambda_function.lambda_function.arn
    ]
  }
}

