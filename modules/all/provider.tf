provider "aws" {
  default_tags {
    tags = {
      CreatedBy = "Terraform",
      Namespace = var.namespace,
      Project = var.project,
      Environment = var.environment
    }
  }
}

terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
    }
  }
}