resource "aws_s3_bucket" "upload" {
  bucket        = "${local.resource_prefix}-upload"
  force_destroy = var.features.s3.can_be_deleted_if_not_empty
}

resource "aws_s3_bucket_versioning" "upload" {
  bucket = aws_s3_bucket.upload.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_notification" "on_upload" {
  bucket = aws_s3_bucket.upload.id

  lambda_function {
    lambda_function_arn = module.lambda_function_on_upload.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [module.lambda_function_on_upload]
}

resource "aws_s3_bucket" "incoming" {
  bucket        = "${local.resource_prefix}-incoming"
  force_destroy = var.features.s3.can_be_deleted_if_not_empty
}

resource "aws_s3_bucket_notification" "on_incoming" {
  bucket = aws_s3_bucket.incoming.id

  lambda_function {
    lambda_function_arn = module.lambda_function_on_incoming.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [module.lambda_function_on_incoming]
}

resource "aws_s3_bucket" "categorized" {
  bucket        = "${local.resource_prefix}-categorized"
  force_destroy = var.features.s3.can_be_deleted_if_not_empty
}

resource "aws_s3_bucket" "files" {
  bucket        = "${local.resource_prefix}-files"
  force_destroy = var.features.s3.can_be_deleted_if_not_empty
}

resource "aws_s3_bucket" "backfill_categories_temp" {
  bucket        = "${local.resource_prefix}-backfill-categories-temp"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backfill_categories_temp" {
  bucket = aws_s3_bucket.backfill_categories_temp.id

  rule {
    id = "remove-old-objects"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 30
    }
  }
}