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
  push_test_user = "sftp-user-testing-prod"
}

run "push_server_exists" {
  command = plan

  assert {
    condition     = length(aws_transfer_server.push_server) == 1
    error_message = "SFTP Transfer Family server for push not found"
  }

  assert {
    condition     = aws_transfer_server.push_server[0].domain == "S3"
    error_message = "SFTP Transfer Family server for push uses the wrong domain"
  }

  assert {
    condition     = aws_transfer_server.push_server[0].endpoint_type == "VPC"
    error_message = "SFTP Transfer Family server for push uses the wrong endpoint_type"
  }
}

run "push_test_user_exists" {
  command = plan

  assert {
    condition     = aws_transfer_ssh_key.push_peer[var.push_test_user].user_name == var.push_test_user
    error_message = "Unexpected user name in SSH key for push test user found"
  }

  assert {
    condition     = aws_transfer_user.push_peer[var.push_test_user].home_directory_type == "LOGICAL"
    error_message = "Unexpected home directory type in transfer user for push test user found"
  }

  assert {
    condition     = aws_transfer_user.push_peer[var.push_test_user].user_name == var.push_test_user
    error_message = "Unexpected user name in transfer user for push test user found"
  }
}