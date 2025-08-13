locals {
  // shared
  resource_prefix = "${var.namespace}-${var.project}-${var.environment}"
  all_peers = {for peer in var.peers_config: peer["id"] => peer}
  all_non_api_peers = { for peer_id, peer in local.all_peers : peer_id => peer if peer["method"] != "api" }
  pull_peers = {for peer_id, peer in local.all_peers : peer_id => peer if peer["method"] == "pull"}
  push_peers = {for peer_id, peer in local.all_peers : peer_id => peer if peer["method"] == "push"}
  email_peers = {for peer_id, peer in local.all_peers : peer_id => peer if peer["method"] == "email"}
  api_peers = {for peer_id, peer in local.all_peers : peer_id => peer if peer["method"] == "api"}
  arch_peers = {
    for peer_id, peer in local.api_peers : peer_id => peer
    if try(peer.config.arch, null) != null
  }
  wise_peers = {
    for peer_id, peer in local.api_peers : peer_id => peer
    if try(peer.config.wise, null) != null
  }
  wise_peers_with_webhook = {
    for peer_id, peer in local.wise_peers : peer_id => peer
    if try(peer.config.wise.events.enabled, false) == true
  }

  // appconfig
  appconfig_extension_url = "http://localhost:2772/applications/${local.resource_prefix}/environments/${var.environment}/configurations/${aws_appconfig_configuration_profile.default.name}"

  // ecr
  docker_registry_address = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.region}.amazonaws.com"

  // lambda
  python_version        = "python3.12"
  image_tag             = formatdate("YYYYMMDDhhmmss", timestamp())

  // ssm
  param_prefix = "${var.namespace}/${var.project}/${var.environment}"

  // transfer family
  default_push_user = "sftp-user-${var.environment}"
  push_config = merge(
    {(local.default_push_user) = { id = local.default_push_user, ssh-public-key = var.sftp_push_default_user_public_key }}, 
    local.push_peers
  )
}