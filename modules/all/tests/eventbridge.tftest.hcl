variables {
  environment = "testing-prod"
  peers_config = [
    {
      id: "bank1",
      name: "Bank 1",
      method: "pull",
      hostname: "sftp.google.com",
      port: 22,
      username: "foo",
      folder: "/files",
      schedule: "0 0 1 1 ? 2300"
    }
  ]
  log_group_transfer_family = {
    name = "/log/group"
    arn  = "arn:aws:logs:us-east-1:123456789012:log-group:/log/group"
  }
  sftp_push_default_user_public_key = ""

  sample_peer = "bank1"
}

run "all_aws_cloudwatch_event_targets_exist" {
  command = plan

  assert {
    condition     = length(aws_cloudwatch_event_target.pull) == length(local.pull_peers)
    error_message = "Missing at least one aws_cloudwatch_event_target to trigger the pull lambdas"
  }
}

run "validate_aws_cloudwatch_event_targets" {
  command = plan

  assert {
    condition     = aws_cloudwatch_event_target.pull[var.sample_peer].event_bus_name == "default"
    error_message = "Found a Eventbridge event not using the default eventbus"
  }

  assert {
    condition     = aws_cloudwatch_event_target.pull[var.sample_peer].input == jsonencode({id = var.sample_peer})
    error_message = "Found a Eventbridge event not using the expected payload"
  }

  assert {
    condition     = aws_cloudwatch_event_target.pull[var.sample_peer].rule == "${var.namespace}-${var.project}-${var.environment}-${var.sample_peer}"
    error_message = "Found a Eventbridge event rule not using the expected name"
  }
}

run "validate_aws_lambda_permissions" {
  command = plan

  assert {
    condition     = length(aws_lambda_permission.allow_eventbridge_pull_trigger) == length(local.pull_peers)
    error_message = "Missing at least one aws_lambda_permission to trigger the pull lambdas"
  }

  assert {
    condition     = length(aws_lambda_permission.allow_eventbridge_api_trigger) == length(local.api_peers)
    error_message = "Missing at least one aws_lambda_permission to trigger the api lambdas"
  }

  assert {
    condition     = aws_lambda_permission.allow_eventbridge_pull_trigger[var.sample_peer].action == "lambda:InvokeFunction"
    error_message = "Found a Eventbridge Lambda permission not setting the expected action"
  }

  assert {
    condition     = aws_lambda_permission.allow_eventbridge_pull_trigger[var.sample_peer].function_name == "${var.namespace}-${var.project}-${var.environment}-pull"
    error_message = "Found a Eventbridge Lambda permission not setting the expected function name"
  }

  assert {
    condition     = aws_lambda_permission.allow_eventbridge_pull_trigger[var.sample_peer].principal == "events.amazonaws.com"
    error_message = "Found a Eventbridge Lambda permission not setting the expected principal"
  }

  assert {
    condition     = aws_lambda_permission.allow_eventbridge_pull_trigger[var.sample_peer].statement_id == "${var.namespace}-${var.project}-${var.environment}-allow-cloudwatch-${var.sample_peer}"
    error_message = "Found a Eventbridge Lambda permission not setting the expected statement id"
  }
}