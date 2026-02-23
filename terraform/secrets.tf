# Secrets for rotated IAM user access keys
resource "aws_secretsmanager_secret" "access_key" {
  name        = "${var.env_name}-${var.lambda_name}-access-key"
  description = "Access Key ID for copilot usage lambda IAM user"
  recovery_window_in_days        = 0    // Secret will be deleted immediately
  force_overwrite_replica_secret = true // Allow overwriting the secret in case of changes
}

resource "aws_secretsmanager_secret" "secret_key" {
  name        = "${var.env_name}-${var.lambda_name}-secret-key"
  description = "Secret Access Key for copilot usage lambda IAM user"
  recovery_window_in_days        = 0    // Secret will be deleted immediately
  force_overwrite_replica_secret = true // Allow overwriting the secret in case of changes
}
