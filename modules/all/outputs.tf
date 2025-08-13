output "REGION" {
  value = data.aws_region.current.region
}

output "PUSH_SERVER_PUBLIC_IP" {
  value = var.features.push_server.lock_elastic_ip ? aws_eip.fixed[0].public_ip : aws_eip.temporary[0].public_ip
}

output "DEFAULT_PUSH_USER" {
  value = local.default_push_user
}

output "BUCKET_NAME_UPLOAD" {
  value = aws_s3_bucket.upload.id
}

output "BUCKET_NAME_INCOMING" {
  value = aws_s3_bucket.incoming.id
}

output "BUCKET_NAME_CATEGORIZED" {
  value = aws_s3_bucket.categorized.id
}

output "BUCKET_NAME_FILES" {
  value = aws_s3_bucket.files.id
}

output "LAMBDA_FUNCTION_NAME_PULL" {
  value = module.lambda_function_pull.lambda_function_name
}

output "LAMBDA_FUNCTION_NAME_ON_UPLOAD" {
  value = module.lambda_function_on_upload.lambda_function_name
}

output "LAMBDA_FUNCTION_NAME_ON_INCOMING" {
  value = module.lambda_function_on_incoming.lambda_function_name
}

output "LAMBDA_FUNCTION_NAME_ADMIN_TASKS" {
  value = module.lambda_function_admin_tasks.lambda_function_name
}

output "LAMBDA_DOCKER_IMAGE_URL" {
  value = docker_registry_image.lambda.name
}

output "LOG_GROUP_TRANSFER_FAMILY" {
  value = var.features.push_server.enabled ? {
    name: aws_cloudwatch_log_group.transfer_family_push_server[0].name,
    arn: aws_cloudwatch_log_group.transfer_family_push_server[0].arn,
  } : null
}

output "WEBHOOKS" {
  value = concat([
    for peer_id, peer in local.wise_peers_with_webhook : "${peer_id} : POST ${aws_apigatewayv2_stage.events.invoke_url}events/${peer_id}"
  ])
}

output "SECRETS" {
  value = concat([
    for peer_id, peer in local.pull_peers : "${aws_secretsmanager_secret.pull[peer_id].name} : ${aws_secretsmanager_secret.pull[peer_id].arn}"
  ], [
    for peer_id, peer in local.all_non_api_peers : "${aws_secretsmanager_secret.on_upload[peer_id].name} : ${aws_secretsmanager_secret.on_upload[peer_id].arn}"
  ],[
    for peer_id, peer in local.wise_peers: "${aws_secretsmanager_secret.wise[peer_id].name} : ${aws_secretsmanager_secret.wise[peer_id].arn}"
  ],[
    for peer_id, peer in local.arch_peers: "${aws_secretsmanager_secret.arch_client_credentials[peer_id].name} : ${aws_secretsmanager_secret.arch_client_credentials[peer_id].arn}"
  ],[
    for peer_id, peer in local.arch_peers: "${aws_secretsmanager_secret.arch_access_token[peer_id].name} : ${aws_secretsmanager_secret.arch_access_token[peer_id].arn}"
  ],)
}