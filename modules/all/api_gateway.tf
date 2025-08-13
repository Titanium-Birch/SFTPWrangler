resource "aws_apigatewayv2_api" "events" {
  name          = "${local.resource_prefix}-events"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "events" {
  api_id                = aws_apigatewayv2_api.events.id
  integration_type      = "AWS_PROXY"
  integration_uri       = module.lambda_function_apiwebhook.lambda_function_invoke_arn
}

resource "aws_apigatewayv2_stage" "events" {
  api_id      = aws_apigatewayv2_api.events.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_route" "events" {
  for_each              = local.wise_peers_with_webhook
  api_id                = aws_apigatewayv2_api.events.id
  route_key             = "POST /events/${each.key}"
  target                = "integrations/${aws_apigatewayv2_integration.events.id}"
}

resource "terraform_data" "wise_webhooks" {
  for_each  = local.wise_peers_with_webhook

  input = {
    profile = each.value.config.wise.profile
    environment = var.environment
  }

  provisioner "local-exec" {
    command = <<EOT
      ./${path.module}/scripts/create_wise_webhook.sh ${each.value.config.wise.profile} ${each.key} ${aws_apigatewayv2_stage.events.invoke_url}events/${each.key} ${self.input.environment}
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<EOT
      ./${path.module}/scripts/delete_wise_webhook.sh ${self.input.profile} ${each.key} ${self.input.environment}
    EOT
  }

  depends_on = [aws_apigatewayv2_route.events]
  triggers_replace = timestamp()
}

resource "aws_lambda_permission" "apiwebhook" {
  statement_id  = "${local.resource_prefix}-allow-apiwebhook-api-gateway"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_function_apiwebhook.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.events.execution_arn}/*/*"
}