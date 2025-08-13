# create a secret for holding the SSH private key for each peer that must be pulled
resource "aws_secretsmanager_secret" "pull" {
  for_each                  = local.pull_peers
  name                      = "lambda/pull/${local.param_prefix}/${each.key}"
  recovery_window_in_days   = 0
}

# leave the secret value empty initially but also make sure we allow manually edits
resource "aws_secretsmanager_secret_version" "pull" {
  for_each      = local.pull_peers
  secret_id     = aws_secretsmanager_secret.pull[each.key].id
  secret_string = "CHANGE ME"

  lifecycle {
    ignore_changes  = [
      secret_string,
    ]
  }
}

# create secrets for each peer, which optionally may be used to keep
# a PGP private key for decrypting the peer's files (not needed for api peers)
resource "aws_secretsmanager_secret" "on_upload" {
  for_each                  = local.all_non_api_peers
  name                      = "lambda/on_upload/pgp/${local.param_prefix}/${each.key}"
  recovery_window_in_days   = 0
}

# leave the secret value empty initially but also make sure we allow manually edits
resource "aws_secretsmanager_secret_version" "on_upload" {
  for_each      = local.all_non_api_peers
  secret_id     = aws_secretsmanager_secret.on_upload[each.key].id
  secret_string = "CHANGE ME"

  lifecycle {
    ignore_changes  = [
      secret_string,
    ]
  }
}

# create a secret for (some) API peers
resource "aws_secretsmanager_secret" "wise" {
  for_each                  = local.wise_peers
  name                      = "lambda/api/${local.param_prefix}/wise/${each.key}"
  recovery_window_in_days   = 0
}

resource "aws_secretsmanager_secret_version" "wise" {
  for_each      = local.wise_peers
  secret_id     = aws_secretsmanager_secret.wise[each.key].id
  secret_string = jsonencode({
    api_key: ""
  })

  lifecycle {
    ignore_changes  = [
      secret_string,
    ]
  }
}

# arch client credentials
resource "aws_secretsmanager_secret" "arch_client_credentials" {
  for_each                  = local.arch_peers
  name                      = "lambda/api/${local.param_prefix}/arch/${each.key}/client_credentials"
  recovery_window_in_days   = 0
}

resource "aws_secretsmanager_secret_version" "arch_client_credentials" {
  for_each      = local.arch_peers
  secret_id     = aws_secretsmanager_secret.arch_client_credentials[each.key].id
  secret_string = jsonencode({
    clientId: "",
    clientSecret: ""
  })

  lifecycle {
    ignore_changes  = [
      secret_string,
    ]
  }
}

# rotating arch access token
resource "aws_secretsmanager_secret" "arch_access_token" {
  for_each                  = local.arch_peers
  name                      = "lambda/api/${local.param_prefix}/arch/${each.key}/auth"
  recovery_window_in_days   = 0
}

resource "aws_secretsmanager_secret_version" "arch_access_token" {
  for_each      = local.arch_peers
  secret_id     = aws_secretsmanager_secret.arch_access_token[each.key].id
  secret_string = <<EOF
{
"accessToken": "",
"expiresIn": 0,
"tokenType": "Bearer"
}
EOF

  lifecycle {
    ignore_changes = all
  }
}

resource "aws_secretsmanager_secret_rotation" "arch_access_token" {
  for_each            = local.arch_peers
  secret_id           = aws_secretsmanager_secret.arch_access_token[each.key].id
  rotation_lambda_arn = module.lambda_function_rotate_secrets[each.key].lambda_function_arn

  rotation_rules {
    schedule_expression = "rate(4 hour)"
  }
}