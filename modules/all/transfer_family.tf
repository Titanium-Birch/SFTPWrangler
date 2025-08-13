resource "tls_private_key" "push_host" {
  algorithm = "RSA"
}

resource "aws_eip" "fixed" {
  count  = var.features.push_server.lock_elastic_ip ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${local.resource_prefix}-fixed" }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_eip" "temporary" {
  count = var.features.push_server.lock_elastic_ip ? 0 : 1
  tags  = { Name = "${local.resource_prefix}-temporary" }
}

resource "aws_transfer_server" "push_server" {
  count                  = var.features.push_server.enabled ? 1 : 0
  identity_provider_type = "SERVICE_MANAGED"
  endpoint_type          = "VPC"

  endpoint_details {
    address_allocation_ids = [var.features.push_server.lock_elastic_ip ? aws_eip.fixed[0].id : aws_eip.temporary[0].id]
    subnet_ids             = [aws_subnet.public.id]
    security_group_ids     = [aws_security_group.sftp.id]
    vpc_id                 = aws_vpc.default.id
  }

  s3_storage_options {
    directory_listing_optimization = "ENABLED"
  }

  logging_role                = aws_iam_role.push_log[count.index].arn
  structured_log_destinations = ["${aws_cloudwatch_log_group.transfer_family_push_server[count.index].arn}:*"]

  host_key = tls_private_key.push_host.private_key_openssh
  tags     = { Name = "${local.resource_prefix}-push" }
}

resource "aws_iam_role" "push_peer" {
  for_each = local.push_config
  name     = "${local.resource_prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "transfer.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "push_peer" {
  for_each    = local.push_config
  name        = "${local.resource_prefix}-${each.key}"
  description = "Restricts S3 access for: ${each.key}"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid = "AllowListingOfBucket",
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ],
        Effect   = "Allow",
        Resource = aws_s3_bucket.upload.arn
      },
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:DeleteObjectVersion",
          "s3:GetObjectVersion",
          "s3:GetObjectACL",
          "s3:PutObjectACL"
        ],
        Effect   = "Allow",
        Resource = "${aws_s3_bucket.upload.arn}/${each.key}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "push_peer" {
  for_each   = local.push_config
  policy_arn = aws_iam_policy.push_peer[each.key].arn
  role       = aws_iam_role.push_peer[each.key].name
}

resource "aws_transfer_user" "push_peer" {
  for_each = var.features.push_server.enabled ? local.push_config : tomap({})

  server_id           = aws_transfer_server.push_server[0].id
  user_name           = each.key
  role                = aws_iam_role.push_peer[each.key].arn
  home_directory_type = "LOGICAL"
  home_directory_mappings {
    entry  = "/"
    target = "/${aws_s3_bucket.upload.id}/${each.key}"
  }
}

resource "aws_transfer_ssh_key" "push_peer" {
  for_each  = var.features.push_server.enabled ? local.push_config : tomap({})
  server_id = aws_transfer_server.push_server[0].id
  user_name = aws_transfer_user.push_peer[each.key].user_name
  body      = each.value["ssh-public-key"]
}
