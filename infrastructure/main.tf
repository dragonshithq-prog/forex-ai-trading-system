# =============================================================================
# Terraform — Main Configuration
# Forex AI Trading Platform — AWS Infrastructure
# =============================================================================
# Backend state stored in S3 with DynamoDB lock table
# Run: terraform init -backend-config="bucket=<your-tf-state-bucket>"
# =============================================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state: S3 + DynamoDB lock
  # Configure via: terraform init -backend-config=backend.hcl
  # or environment variable TF_CLI_ARGS_init="-backend-config=..."
  backend "s3" {
    bucket         = "forex-trading-terraform-state"      # REPLACE with your bucket
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "forex-trading-terraform-locks"      # DynamoDB table for state locking
    # Use IAM role for CI/CD
    # role_arn     = "arn:aws:iam::ACCOUNT_ID:role/TerraformRole"
  }
}

# ── AWS Provider ───────────────────────────────────────────────────────────────
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "forex-trading-platform"
    }
  }
}

# Secondary region provider (for cross-region backups)
provider "aws" {
  alias  = "backup"
  region = var.backup_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ── Kubernetes Provider (configured after EKS is created) ─────────────────────
provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

# ── Helm Provider ──────────────────────────────────────────────────────────────
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

# ── Data Sources ───────────────────────────────────────────────────────────────
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# ── Local Values ───────────────────────────────────────────────────────────────
locals {
  name        = "${var.project_name}-${var.environment}"
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name

  # AZs: use first 2 available
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
