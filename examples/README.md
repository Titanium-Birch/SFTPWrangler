# SFTP Wrangler Examples

This directory contains example configurations showing how to use the SFTP Wrangler Terraform module in your own projects.

## Prerequisites

This project uses a devcontainer environment with all tools pre-installed. Terraform and AWS CLI are already available in the development environment.

### Configure AWS Credentials

Configure your credentials using:

```bash
aws configure
```

You'll be prompted for:
- AWS Access Key ID
- AWS Secret Access Key  
- Default region (e.g., `us-east-1`)
- Default output format (e.g., `json`)

**Alternative methods:**
- **Environment variables:** Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION`
- **AWS SSO:** Use `aws configure sso` and `aws sso login --profile your-profile-name`

### Required AWS Permissions

Ensure your AWS credentials have the following permissions:
- EC2 (VPC, Security Groups, Elastic IPs)
- S3 (Bucket creation and management)
- Lambda (Function creation and management)
- IAM (Role and policy management)
- API Gateway
- Transfer Family (for SFTP functionality)
- Secrets Manager
- CloudWatch
- EventBridge
- ECR (Elastic Container Registry)

## Basic Example

The `basic/` directory contains a complete example setup that demonstrates all major features of the SFTP Wrangler module.

### Quick Start

1. Navigate to the basic example:
   ```bash
   cd examples/basic
   ```

2. Initialize Terraform:
   ```bash
   terraform init
   ```

3. Review the planned changes:
   ```bash
   terraform plan
   ```

4. Deploy the infrastructure:
   ```bash
   terraform apply
   ```

5. When you're done testing, destroy the infrastructure:
   ```bash
   terraform destroy
   ```

### Example Configuration

The basic example includes three types of data ingestion peers:

1. **Pull Peer** (`peer1`): Connects to an external SFTP server to pull data
2. **API Peer - Wise** (`peer2`): Integrates with Wise API for financial data
3. **API Peer - Arch** (`peer3`): Integrates with Arch API for various financial entities

### Customizing for Your Project

To use SFTP Wrangler in your own project:

1. **Create a new Terraform configuration** in your project directory
2. **Reference the module** using the source from your preferred location:

```hcl
module "sftpwrangler" {
  source = "git@github.com:your-org/SFTPWrangler.git//modules/all?ref=main"
  
  # Required variables
  environment  = "production"  # or "staging", "dev", etc.
  peers_config = [
    # Your peer configurations here
  ]
  
  # Optional variables
  namespace = "my-company"
  project   = "financial-data"
  
  # Feature configuration
  features = {
    push_server = {
      enabled           = true
      lock_elastic_ip   = true  # Set to true for production
    }
    s3 = {
      can_be_deleted_if_not_empty = false  # Set to false for production
      create_backups              = true
    }
  }
}
```

3. **Configure your peers** based on your data sources:

#### Pull Configuration (SFTP)

> **⚠️ SECURITY**: See [SFTP Security Best Practices](../README.md#sftp-security-best-practices) for fingerprint configuration requirements.

```hcl
{
  id       = "bank-sftp"
  name     = "Bank SFTP Server"
  method   = "pull"
  hostname = "sftp.bank.com"
  port     = 22
  username = "your-username"
  folder   = "/incoming"
  # 🔐 REQUIRED for production security
  host-sha256-fingerprints = ["SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8"]
  schedule = "0 2 * * *"  # Daily at 2 AM
  categories = [
    {
      category_id       = "transactions"
      filename_patterns = ["transaction*.csv"]
      transformations   = ["RemoveNewlinesInCsvFieldsTransformer"]
    }
  ]
}
```

#### Push Configuration (SFTP Server)
```hcl
{
  id              = "partner-push"
  name            = "Partner Push Access"
  method          = "push"
  ssh-public-key  = file("path/to/partner-public-key.pub")
  categories = [
    {
      category_id       = "reports"
      filename_patterns = ["*.csv"]
    }
  ]
}
```

#### API Configuration
```hcl
{
  id     = "wise-integration"
  name   = "Wise API"
  method = "api"
  schedule = "0 */6 * * *"  # Every 6 hours
  config = {
    wise = {
      profile      = "your-profile-id"
      sub_accounts = ["account1", "account2"]
      events = {
        enabled = true
      }
    }
  }
}
```

### Backend Configuration

For production use, configure a remote backend to store Terraform state:

```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "sftpwrangler/terraform.tfstate"
    region = "us-east-1"
  }
}
```

### Environment-Specific Configurations

Consider using Terraform workspaces or separate directories for different environments:

```bash
# Using workspaces
terraform workspace new production
terraform workspace new staging

# Or separate directories
mkdir -p environments/{dev,staging,prod}
```

## Security Considerations

1. **Secrets Management**: The module uses AWS Secrets Manager for storing sensitive data like API keys and SFTP credentials
2. **VPC Isolation**: All resources are deployed within a dedicated VPC
3. **IAM Roles**: Follows principle of least privilege for all IAM roles
4. **Encryption**: S3 buckets and data in transit are encrypted

## Monitoring and Troubleshooting

After deployment, you can monitor your SFTP Wrangler infrastructure through:

- **CloudWatch Logs**: Lambda function logs and error tracking
- **CloudWatch Metrics**: Custom metrics for data ingestion monitoring
- **S3 Buckets**: Check the created buckets for incoming, processed, and error data
- **Transfer Family**: Monitor SFTP connections and file transfers

## Support

For issues, questions, or contributions, please refer to the main repository documentation and issue tracker.
