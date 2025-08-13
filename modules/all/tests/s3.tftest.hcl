variables {
  environment = "testing-prod"
  peers_config = [
    {
      id: "bank1",
      name: "Bank 1",
      method: "pull",
      hostname: "sftp.google.com",
      port: 22,
      username: "foo",
      folder: "/files",
      schedule: "0 0 1 1 ? 2300"
    }
  ]
  log_group_transfer_family = {
    name = "/log/group"
    arn  = "arn:aws:logs:us-east-1:123456789012:log-group:/log/group"
  }
  sftp_push_default_user_public_key = ""
}

run "upload_bucket_exists" {
  command = plan

  assert {
    condition     = aws_s3_bucket.upload.bucket == "${var.namespace}-${var.project}-${var.environment}-upload"
    error_message = "S3 upload bucket name did not match expected"
  }
}

run "on_upload_trigger_exists" {
  command = plan

  assert {
    condition     = length(aws_s3_bucket_notification.on_upload.lambda_function) == 1
    error_message = "No bucket notification for the upload bucket found"
  }
  
  assert {
    condition     = contains(aws_s3_bucket_notification.on_upload.lambda_function[0].events, "s3:ObjectCreated:*")
    error_message = "Upload bucket does not notify about s3:ObjectCreated .."
  }
}

run "incoming_bucket_exists" {
  command = plan

  assert {
    condition     = aws_s3_bucket.incoming.bucket == "${var.namespace}-${var.project}-${var.environment}-incoming"
    error_message = "S3 incoming bucket name did not match expected"
  }
}

run "files_bucket_exists" {
  command = plan

  assert {
    condition     = aws_s3_bucket.files.bucket == "${var.namespace}-${var.project}-${var.environment}-files"
    error_message = "S3 files bucket name did not match expected"
  }
}

run "on_incoming_trigger_exists" {
  command = plan

  assert {
    condition     = length(aws_s3_bucket_notification.on_incoming.lambda_function) == 1
    error_message = "No bucket notification for the incoming bucket found"
  }
  
  assert {
    condition     = contains(aws_s3_bucket_notification.on_incoming.lambda_function[0].events, "s3:ObjectCreated:*")
    error_message = "Incoming bucket does not notify about s3:ObjectCreated .."
  }
}