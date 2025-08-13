resource "aws_cloudwatch_event_rule" "pull" {
    for_each                = local.pull_peers
    name                    = "${local.resource_prefix}-${each.key}"
    description             = "triggers SFTP pull for ${each.value["name"]}"
    schedule_expression     = "cron(${each.value["schedule"]})"
    depends_on              = [aws_s3_bucket_notification.on_upload, aws_s3_bucket_notification.on_incoming]

    tags                    = { Peer = "${each.value["name"]}" }
}

resource "aws_cloudwatch_event_rule" "api" {
    for_each                = local.api_peers
    name                    = "${local.resource_prefix}-${each.key}"
    description             = "triggers API invocation for ${each.value["name"]}"
    schedule_expression     = "cron(${each.value["schedule"]})"
    depends_on              = [aws_s3_bucket_notification.on_upload, aws_s3_bucket_notification.on_incoming]

    tags                    = { Peer = "${each.value["name"]}" }
}

resource "aws_cloudwatch_event_target" "pull" {
    for_each = local.pull_peers
    arn      = module.lambda_function_pull.lambda_function_arn
    rule     = aws_cloudwatch_event_rule.pull[each.key].name
    input    = jsonencode({
        id = each.key,
    })
}

resource "aws_cloudwatch_event_target" "api" {
    for_each = local.api_peers
    arn      = module.lambda_function_api.lambda_function_arn
    rule     = aws_cloudwatch_event_rule.api[each.key].name
    input    = jsonencode({
        id = each.key,
    })
}

resource "aws_lambda_permission" "allow_eventbridge_pull_trigger" {
    for_each        = local.pull_peers
    statement_id    = "${local.resource_prefix}-allow-cloudwatch-${each.key}"
    action          = "lambda:InvokeFunction"
    function_name   = module.lambda_function_pull.lambda_function_name
    principal       = "events.amazonaws.com"
    source_arn      = aws_cloudwatch_event_rule.pull[each.key].arn
}

resource "aws_lambda_permission" "allow_eventbridge_api_trigger" {
    for_each        = local.api_peers
    statement_id    = "${local.resource_prefix}-allow-cloudwatch-${each.key}"
    action          = "lambda:InvokeFunction"
    function_name   = module.lambda_function_api.lambda_function_name
    principal       = "events.amazonaws.com"
    source_arn      = aws_cloudwatch_event_rule.api[each.key].arn
}