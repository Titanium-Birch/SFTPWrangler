resource "aws_cloudwatch_log_group" "lambda_pull" {
  name              = "/aws/lambda/${local.resource_prefix}-pull"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_api" {
  name              = "/aws/lambda/${local.resource_prefix}-api"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_apiwebhook" {
  name              = "/aws/lambda/${local.resource_prefix}-apiwebhook"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_on_upload" {
  name              = "/aws/lambda/${local.resource_prefix}-on-upload"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_on_incoming" {
  name              = "/aws/lambda/${local.resource_prefix}-on-incoming"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_admin_tasks" {
  name              = "/aws/lambda/${local.resource_prefix}-admin-tasks"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "lambda_rotate_secrets" {
  for_each          = local.arch_peers
  name              = "/aws/lambda/${local.resource_prefix}-rotate-${each.key}"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_cloudwatch_log_group" "transfer_family_push_server" {
  count             = var.features.push_server.enabled ? 1 : 0
  name              = "/aws/transfer-family/${local.resource_prefix}-push"
  retention_in_days = 90

  lifecycle {
    prevent_destroy = false
  }
}