resource "aws_appconfig_application" "default" {
  name        = local.resource_prefix
}

resource "aws_appconfig_configuration_profile" "default" {
  application_id      = aws_appconfig_application.default.id
  name                = "${local.resource_prefix}-peers"
  location_uri        = "hosted"
}

resource "aws_appconfig_hosted_configuration_version" "default" {
  application_id            = aws_appconfig_application.default.id
  configuration_profile_id  = aws_appconfig_configuration_profile.default.configuration_profile_id
  content_type              = "application/json"
  content                   = jsonencode(var.peers_config)
}

resource "aws_appconfig_environment" "default" {
  name            = var.environment
  application_id  = aws_appconfig_application.default.id
}

resource "aws_appconfig_deployment" "default" {
  application_id            = aws_appconfig_application.default.id
  environment_id            = aws_appconfig_environment.default.environment_id
  configuration_profile_id  = aws_appconfig_configuration_profile.default.configuration_profile_id
  configuration_version     = aws_appconfig_hosted_configuration_version.default.version_number
  deployment_strategy_id    = "AppConfig.AllAtOnce"
}