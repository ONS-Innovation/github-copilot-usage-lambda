variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "aws_access_key_id" {
  description = "AWS Access Key ID"
  type        = string
}

variable "aws_secret_access_key" {
  description = "AWS Secret Access Key"
  type        = string
}

variable "aws_secret_name" {
  description = "The path to the AWS Secret Manager resource which contains the Github App .pem file"
  type        = string
}

variable "env_name" {
  description = "AWS environment"
  type        = string
  default     = "sdp-dev"
}

variable "lambda_name" {
  description = "AWS Lambda Function Name"
  type        = string
  default     = "lambda-function"
}

variable "lambda_arch" {
  description = "AWS Lambda Architecture"
  type        = string
  default     = "x86_64"
}

variable "lambda_timeout" {
  description = "AWS Lambda Timeout Value in Seconds"
  type        = number
  default     = 60
}

variable "schedule" {
  description = "The schedule to trigger the lambda, rate(value minutes|hours|days) or cron(minutes hours day-of-month month day-of-week year)"
  type        = string
  default     = "cron(0 6 ? * 2 *)" // every Monday at 6am
}

variable "log_retention_days" {
  description = "Lambda log retention in days"
  type        = number
  default     = 30
}

variable "github_org" {
  description = "Github Organisation"
  type        = string
  default     = "ONS-Innovation"
}

variable "github_app_client_id" {
  description = "Github App Client ID"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "ecr_repository" {
  description = "Name of the ECR repository containing the Lambda image"
  type        = string
}

variable "container_ver" {
  description = "Container tag"
  type        = string
  default     = "v1.0.0"
}

variable "project_tag" {
  description = "Project"
  type        = string
  default     = "SDP"
}

variable "team_owner_tag" {
  description = "Team Owner"
  type        = string
  default     = "Knowledge Exchange Hub"
}

variable "business_owner_tag" {
  description = "Business Owner"
  type        = string
  default     = "DST"
}

locals {
  lambda_repo = "${var.env_name}-${var.lambda_name}"
}