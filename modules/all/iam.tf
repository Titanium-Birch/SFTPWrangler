# Lambda: pull

resource "aws_iam_role" "lambda_pull" {
  name = "${local.resource_prefix}-lambda-pull"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_pull" {
  name = "${local.resource_prefix}-lambda-pull"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = "${aws_cloudwatch_log_group.lambda_pull.arn}:*"
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ],
        Effect   = "Allow",
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:*"
        ],
        Resource = [
          "${aws_s3_bucket.upload.arn}",
          "${aws_s3_bucket.upload.arn}/*"
        ]
      },
      {
        Effect   = "Allow",
        Action = [
          "appconfig:GetLatestConfiguration",
          "appconfig:StartConfigurationSession"
        ],
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_pull" {
  policy_arn = aws_iam_policy.lambda_pull.arn
  role       = aws_iam_role.lambda_pull.name
}

# Lambda: api

resource "aws_iam_role" "lambda_api" {
  name = "${local.resource_prefix}-lambda-api"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_api" {
  name = "${local.resource_prefix}-lambda-api"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = [
          "${aws_cloudwatch_log_group.lambda_api.arn}:*",
          "${aws_cloudwatch_log_group.lambda_apiwebhook.arn}:*"
        ]
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ],
        Effect   = "Allow",
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:*"
        ],
        Resource = [
          "${aws_s3_bucket.upload.arn}",
          "${aws_s3_bucket.upload.arn}/*",
          "${aws_s3_bucket.files.arn}",
          "${aws_s3_bucket.files.arn}/*"
        ]
      },
      {
        Effect   = "Allow",
        Action = [
          "appconfig:GetLatestConfiguration",
          "appconfig:StartConfigurationSession"
        ],
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_api" {
  policy_arn = aws_iam_policy.lambda_api.arn
  role       = aws_iam_role.lambda_api.name
}

# Lambda: on_upload

resource "aws_iam_role" "lambda_on_upload" {
  name = "${local.resource_prefix}-lambda-on-upload"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_on_upload" {
  name = "${local.resource_prefix}-lambda-on-upload"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = "${aws_cloudwatch_log_group.lambda_on_upload.arn}:*"
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ],
        Effect   = "Allow",
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:*"
        ],
        Resource = [
          "${aws_s3_bucket.upload.arn}",
          "${aws_s3_bucket.upload.arn}/*",
          "${aws_s3_bucket.incoming.arn}",
          "${aws_s3_bucket.incoming.arn}/*"
        ]
      },
      {
        Effect   = "Allow",
        Action = [
          "appconfig:GetLatestConfiguration",
          "appconfig:StartConfigurationSession"
        ],
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "on_upload" {
  policy_arn = aws_iam_policy.lambda_on_upload.arn
  role       = aws_iam_role.lambda_on_upload.name
}


# Lambda: on_incoming

resource "aws_iam_role" "lambda_on_incoming" {
  name = "${local.resource_prefix}-lambda-on-incoming"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_on_incoming" {
  name = "${local.resource_prefix}-lambda-on-incoming"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = "${aws_cloudwatch_log_group.lambda_on_incoming.arn}:*"
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ],
        Effect   = "Allow",
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:*"
        ],
        Resource = [
          "${aws_s3_bucket.incoming.arn}",
          "${aws_s3_bucket.incoming.arn}/*",
          "${aws_s3_bucket.categorized.arn}",
          "${aws_s3_bucket.categorized.arn}/*",
        ]
      },
      {
        Effect   = "Allow",
        Action = [
          "appconfig:GetLatestConfiguration",
          "appconfig:StartConfigurationSession"
        ],
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "on_incoming" {
  policy_arn = aws_iam_policy.lambda_on_incoming.arn
  role       = aws_iam_role.lambda_on_incoming.name
}

# Lambda: admin_tasks

resource "aws_iam_role" "lambda_admin_tasks" {
  name = "${local.resource_prefix}-lambda-admin-tasks"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_admin_tasks" {
  name = "${local.resource_prefix}-lambda-admin-tasks"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = "${aws_cloudwatch_log_group.lambda_admin_tasks.arn}:*"
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ],
        Effect   = "Allow",
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:*"
        ],
        Resource = [
          "${aws_s3_bucket.upload.arn}",
          "${aws_s3_bucket.upload.arn}/*",
          "${aws_s3_bucket.incoming.arn}",
          "${aws_s3_bucket.incoming.arn}/*",
          "${aws_s3_bucket.categorized.arn}",
          "${aws_s3_bucket.categorized.arn}/*",
          "${aws_s3_bucket.files.arn}",
          "${aws_s3_bucket.files.arn}/*",
          "${aws_s3_bucket.backfill_categories_temp.arn}",
          "${aws_s3_bucket.backfill_categories_temp.arn}/*",
        ]
      },
      {
        Effect   = "Allow",
        Action = [
          "appconfig:GetLatestConfiguration",
          "appconfig:StartConfigurationSession"
        ],
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "admin_tasks" {
  policy_arn = aws_iam_policy.lambda_admin_tasks.arn
  role       = aws_iam_role.lambda_admin_tasks.name
}

# Lambda: rotate_secrets

resource "aws_iam_role" "lambda_rotate_secrets" {
  count = length(local.arch_peers) > 0 ? 1 : 0
  name  = "${local.resource_prefix}-lambda-rotate-secrets-integration"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "lambda_rotate_secrets" {
  count = length(local.arch_peers) > 0 ? 1 : 0
  name  = "${local.resource_prefix}-lambda-rotate-secrets-integration"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ],
        Effect   = "Allow",
        Resource = [for arn in values(aws_cloudwatch_log_group.lambda_rotate_secrets).*.arn : "${arn}:*"]
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter"
        ],
        Resource = ["*"]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:*"
        ],
        Resource = concat(values(aws_secretsmanager_secret.arch_access_token).*.arn, values(aws_secretsmanager_secret.arch_client_credentials).*.arn)
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_rotate_secrets" {
  count       = length(local.arch_peers) > 0 ? 1 : 0
  policy_arn  = aws_iam_policy.lambda_rotate_secrets[count.index].arn
  role        = aws_iam_role.lambda_rotate_secrets[count.index].name
}

# AWS Backup

resource "aws_iam_role" "backup" {
  count              = var.features.s3.create_backups ? 1 : 0
  name               = "${local.resource_prefix}-backup"
  assume_role_policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": ["sts:AssumeRole"],
      "Effect": "allow",
      "Principal": {
        "Service": ["backup.amazonaws.com"]
      }
    }
  ]
}
POLICY
}

resource "aws_iam_role_policy_attachment" "default_backup_policy" {
  count      = var.features.s3.create_backups ? 1 : 0
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
  role       = aws_iam_role.backup[count.index].name
}

resource "aws_iam_role_policy_attachment" "default_restore_policy" {
  count      = var.features.s3.create_backups ? 1 : 0
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
  role       = aws_iam_role.backup[count.index].name
}

resource "aws_iam_role_policy_attachment" "s3_backup_policy" {
  count      = var.features.s3.create_backups ? 1 : 0
  policy_arn = "arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Backup"
  role       = aws_iam_role.backup[count.index].name
}

resource "aws_iam_role_policy_attachment" "s3_restore_policy" {
  count      = var.features.s3.create_backups ? 1 : 0
  policy_arn = "arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Restore"
  role       = aws_iam_role.backup[count.index].name
}

# IAM Role for transfer family push server logging

data "aws_iam_policy_document" "push_server_transfer_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["transfer.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "push_log" {
  count               = var.features.push_server.enabled ? 1 : 0
  name                = "${local.resource_prefix}-push-log"
  assume_role_policy  = data.aws_iam_policy_document.push_server_transfer_assume_role.json
}

resource "aws_iam_policy" "push_log" {
  count   = var.features.push_server.enabled ? 1 : 0
  name    = "${local.resource_prefix}-push_log"

  policy  = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "${aws_cloudwatch_log_group.transfer_family_push_server[count.index].arn}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "push_log" {
  count       = var.features.push_server.enabled ? 1 : 0
  policy_arn  = aws_iam_policy.push_log[count.index].arn
  role        = aws_iam_role.push_log[count.index].name
}

# IAM User and Role for Zapier

resource "aws_iam_user" "zapier" {
  name = "${local.resource_prefix}-zapier"
}

data "aws_iam_policy_document" "zapier_s3" {
  # List to avoid duplicates and put to write into their path
  statement {
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:ListBucket"]
    resources = concat(
      [aws_s3_bucket.upload.arn],
      [for peer_id, peer in local.email_peers : "${aws_s3_bucket.upload.arn}/${peer_id}/*"]
    )
  }
  # List s3 buckets in the bucket selector
  statement {
    effect = "Allow"
    actions = ["s3:ListAllMyBuckets", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::*"]
  }
}

resource "aws_iam_user_policy" "zapier" {
  name   = "${local.resource_prefix}-zapier-s3"
  user   = aws_iam_user.zapier.name
  policy = data.aws_iam_policy_document.zapier_s3.json
}
