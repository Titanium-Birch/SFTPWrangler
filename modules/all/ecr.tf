provider "docker" {
  registry_auth {
    address  = local.docker_registry_address
    username = data.aws_ecr_authorization_token.token.user_name
    password = data.aws_ecr_authorization_token.token.password
  }
}

resource "aws_ecr_repository" "lambda" {
  name                  = "${local.resource_prefix}-lambda"
  force_delete          = true
  image_tag_mutability  = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name

  policy = <<EOF
{
    "rules": [
        {
            "rulePriority": 1,
            "description": "Expire images older than 7 days",
            "selection": {
                "tagStatus": "untagged",
                "countType": "sinceImagePushed",
                "countUnit": "days",
                "countNumber": 7
            },
            "action": {
                "type": "expire"
            }
        }
    ]
}
EOF
}

resource "docker_image" "lambda" {
  name        = "${aws_ecr_repository.lambda.repository_url}:${local.image_tag}"
  build {
    context   = "${path.module}/../.."
  }
  platform    = "linux/amd64"
}

resource "docker_registry_image" "lambda" {
  name = docker_image.lambda.name
}