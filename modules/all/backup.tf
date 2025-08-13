resource "aws_backup_vault" "default" {
  count         = var.features.s3.create_backups ? 1 : 0
  name          = "${local.resource_prefix}-backup-vault"
  force_destroy = true
}

resource "aws_backup_plan" "default" {
  count = var.features.s3.create_backups ? 1 : 0
  name  = "${local.resource_prefix}-backup-plan"

  rule {
    rule_name         = "${local.resource_prefix}-backups"
    target_vault_name = aws_backup_vault.default[count.index].name
    schedule          = "cron(0 12 * * ? *)"

    lifecycle {
      delete_after = 30
    }
  }
}

resource "aws_backup_selection" "upload" {
  count        = var.features.s3.create_backups ? 1 : 0
  iam_role_arn = aws_iam_role.backup[count.index].arn
  name         = "${local.resource_prefix}-s3-upload"
  plan_id      = aws_backup_plan.default[count.index].id

  resources = [
    aws_s3_bucket.upload.arn
  ]
}