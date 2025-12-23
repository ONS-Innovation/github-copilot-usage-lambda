terraform {
  backend "s3" {

  }
}

resource "aws_security_group" "lambda_sg" {
  name        = "${var.lambda_name}_security_group"
  description = "Security group for ${var.lambda_name} Lambda function"
  vpc_id      = data.terraform_remote_state.vpc.outputs.vpc_id
  ingress {
    description = "Allow inbound HTTPS traffic from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"] // Allow HTTPS traffic within VPC
  }
  egress {
    description = "Allow all outbound HTTPS traffic to any destination"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] // Allow all outbound traffic
  }
}

resource "aws_lambda_function" "lambda_function" {
  function_name = var.lambda_name
  timeout       = var.lambda_timeout
  image_uri     = "${data.aws_ecr_repository.profile_lambda_ecr_repo.repository_url}:${var.lambda_version}"
  package_type  = "Image"
  architectures = [var.lambda_arch]
  logging_config {
    log_format = "JSON" // JSON or Text
  }
  vpc_config {
    subnet_ids         = data.terraform_remote_state.vpc.outputs.private_subnets
    security_group_ids = [aws_security_group.lambda_sg.id] // Dedicated security group for Lambda function
  }

  tracing_config {
    mode = "Active"
  }

  reserved_concurrent_executions = 100

  role = aws_iam_role.lambda_function_role.arn

  memory_size = 256

  environment {
    variables = {
      ENVIRONMENT          = var.env_name
      GITHUB_ORG           = var.github_org
      GITHUB_APP_CLIENT_ID = var.github_app_client_id
      AWS_SECRET_NAME      = var.aws_secret_name
      AWS_ACCOUNT_NAME     = var.env_name
    }
  }
}

resource "aws_iam_role" "lambda_function_role" {
  name = "${var.lambda_name}-${var.env_name}-role"

  assume_role_policy = jsonencode({
    "Version" : "2008-10-17",
    Statement = [
      {
        Action = [
          "sts:AssumeRole"
        ]
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "vpc_permissions" {
  name        = "${var.lambda_name}_vpc_permissions"
  description = "IAM policy for VPC permissions for ${var.lambda_name} Lambda function"
  policy      = data.aws_iam_policy_document.vpc_permissions.json
}

resource "aws_iam_role_policy_attachment" "vpc_policy" {
  role       = aws_iam_role.lambda_function_role.name
  policy_arn = aws_iam_policy.vpc_permissions.arn
}

resource "aws_iam_policy" "lambda_logging" {
  name        = "${var.lambda_name}_logging"
  path        = "/"
  description = "IAM policy for logging from a lambda"
  policy      = data.aws_iam_policy_document.lambda_logging.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_function_role.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}

resource "aws_iam_policy" "lambda_s3_policy" {
  name        = "${var.lambda_name}-${var.env_name}-s3-policy"
  description = "IAM policy for S3 access for Lambda function"
  policy      = data.aws_iam_policy_document.lambda_s3_policy.json
}

resource "aws_iam_role_policy_attachment" "s3_policy" {
  role       = aws_iam_role.lambda_function_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

resource "aws_iam_policy" "lambda_secret_manager_policy" {
  name        = "${var.lambda_name}-${var.env_name}-secret-manager-policy"
  description = "IAM policy for Secret Manager access for Lambda function"
  policy      = data.aws_iam_policy_document.lambda_secret_manager_policy.json
}

resource "aws_iam_role_policy_attachment" "secret_manager_policy" {
  role       = aws_iam_role.lambda_function_role.name
  policy_arn = aws_iam_policy.lambda_secret_manager_policy.arn
}

resource "aws_iam_policy" "lambda_eventbridge_policy" {
  name        = "${var.lambda_name}-${var.env_name}-eventbridge-policy"
  description = "IAM policy to allow EventBridge to invoke Lambda function"
  policy      = data.aws_iam_policy_document.lambda_eventbridge_policy.json
}

resource "aws_iam_role_policy_attachment" "eventbridge_policy" {
  role       = aws_iam_role.lambda_function_role.name
  policy_arn = aws_iam_policy.lambda_eventbridge_policy.arn
}

resource "aws_cloudwatch_log_group" "loggroup" {
  name              = "/aws/lambda/${aws_lambda_function.lambda_function.function_name}"
  retention_in_days = var.log_retention_days
}