module "lambda_function_pull" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 300
  function_name                     = "${local.resource_prefix}-pull"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_pull.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["pull.app.handler"]

  environment_variables = {
    AWS_APPCONFIG_EXTENSION = "true"
    APP_CONFIG_PEERS_URL    = local.appconfig_extension_url
    BUCKET_NAME_UPLOAD      = aws_s3_bucket.upload.id
    METRIC_NAMESPACE        = local.resource_prefix
    LOG_LEVEL               = "INFO"
  }

  allowed_triggers = {
    AnyRule = {
      principal  = "events.amazonaws.com"
      source_arn = "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/*"
    }
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_pull, docker_registry_image.lambda ]
}

module "lambda_function_api" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 300
  function_name                     = "${local.resource_prefix}-api"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_api.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["api.app.handler"]

  environment_variables = {
    ENVIRONMENT             = var.environment
    AWS_APPCONFIG_EXTENSION = "true"
    APP_CONFIG_PEERS_URL    = local.appconfig_extension_url
    BUCKET_NAME_UPLOAD      = aws_s3_bucket.upload.id
    BUCKET_NAME_FILES       = aws_s3_bucket.files.id
    METRIC_NAMESPACE        = local.resource_prefix
    LOG_LEVEL               = "INFO"
  }

  allowed_triggers = {
    AnyRule = {
      principal  = "events.amazonaws.com"
      source_arn = "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/*"
    }
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_api, docker_registry_image.lambda ]
}

module "lambda_function_apiwebhook" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 30
  function_name                     = "${local.resource_prefix}-apiwebhook"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_api.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["api.app.webhook_handler"]

  environment_variables = {
    ENVIRONMENT             = var.environment
    AWS_APPCONFIG_EXTENSION = "true"
    APP_CONFIG_PEERS_URL    = local.appconfig_extension_url
    BUCKET_NAME_UPLOAD      = aws_s3_bucket.upload.id
    METRIC_NAMESPACE        = local.resource_prefix
    LOG_LEVEL               = "INFO"
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_apiwebhook, docker_registry_image.lambda ]
}

module "lambda_function_on_upload" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 60
  function_name                     = "${local.resource_prefix}-on-upload"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_on_upload.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["on_upload.app.handler"]

  environment_variables = {
    BUCKET_NAME_UPLOAD    = aws_s3_bucket.upload.id
    BUCKET_NAME_INCOMING  = aws_s3_bucket.incoming.id
    METRIC_NAMESPACE      = local.resource_prefix
    LOG_LEVEL             = "INFO"
  }

  allowed_triggers = {
    AllowUploadBucket = {
      service    = "s3"
      source_arn = aws_s3_bucket.upload.arn
    }
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_on_upload, docker_registry_image.lambda ]
}

module "lambda_function_on_incoming" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 300
  function_name                     = "${local.resource_prefix}-on-incoming"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_on_incoming.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["on_incoming.app.handler"]

  environment_variables = {
    AWS_APPCONFIG_EXTENSION = "true"
    APP_CONFIG_PEERS_URL    = local.appconfig_extension_url
    BUCKET_NAME_CATEGORIZED = aws_s3_bucket.categorized.id
    METRIC_NAMESPACE        = local.resource_prefix
    LOG_LEVEL               = "INFO"
  }

  allowed_triggers = {
    AllowUploadBucket = {
      service    = "s3"
      source_arn = aws_s3_bucket.incoming.arn
    }
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_on_incoming, docker_registry_image.lambda ]
}

module "lambda_function_admin_tasks" {
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 900
  function_name                     = "${local.resource_prefix}-admin-tasks"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_admin_tasks.arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["admin_tasks.app.handler"]

  environment_variables = {
    AWS_APPCONFIG_EXTENSION               = "true"
    APP_CONFIG_PEERS_URL                  = local.appconfig_extension_url
    BUCKET_NAME_INCOMING                  = aws_s3_bucket.incoming.id
    BUCKET_NAME_CATEGORIZED               = aws_s3_bucket.categorized.id
    BUCKET_NAME_BACKFILL_CATEGORIES_TEMP  = aws_s3_bucket.backfill_categories_temp.id
    BUCKET_NAME_UPLOAD                    = aws_s3_bucket.upload.id
    BUCKET_NAME_FILES                     = aws_s3_bucket.files.id
    METRIC_NAMESPACE                      = local.resource_prefix
    LOG_LEVEL                             = "INFO"
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_admin_tasks, docker_registry_image.lambda ]
}

module "lambda_function_rotate_secrets" {
  for_each                          = local.arch_peers
  source                            = "terraform-aws-modules/lambda/aws"
  version                           = "~> 7.0"
  timeout                           = 30
  function_name                     = "${local.resource_prefix}-rotate-${each.key}"
  runtime                           = local.python_version
  create_sam_metadata               = true
  publish                           = true
  lambda_role                       = aws_iam_role.lambda_rotate_secrets[0].arn
  create_role                       = false
  use_existing_cloudwatch_log_group = true

  create_package                    = false
  package_type                      = "Image"
  image_uri                         = docker_registry_image.lambda.name
  image_config_command              = ["rotate_secrets.app.handler"]

  environment_variables = {
    METRIC_NAMESPACE                            = local.resource_prefix
    ROTABLE_SECRET_ARN                          = aws_secretsmanager_secret.arch_access_token[each.key].arn
    SSM_KEY_CLIENT_CREDENTIALS                  = "/aws/reference/secretsmanager/${aws_secretsmanager_secret.arch_client_credentials[each.key].name}"
    ROTATOR_TYPE                                = "arch"
    ROTATOR_CONTEXT                             = each.key
    LOG_LEVEL                                   = "INFO"
  }

  allowed_triggers = {
    AllowRotation = {
      principal = "secretsmanager.amazonaws.com"
    }
  }

  depends_on  = [ aws_cloudwatch_log_group.lambda_rotate_secrets ]
}