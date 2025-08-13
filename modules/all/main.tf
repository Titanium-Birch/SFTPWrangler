data "aws_regions" "all" {
  all_regions = true
}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ecr_authorization_token" "token" {}