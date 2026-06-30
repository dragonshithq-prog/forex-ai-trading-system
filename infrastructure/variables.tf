# =============================================================================
# Terraform Variables — Forex AI Trading Platform
# =============================================================================

# ── Core ───────────────────────────────────────────────────────────────────────
variable "aws_region" {
  description = "Primary AWS region for all resources"
  type        = string
  default     = "us-east-1"
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "Must be a valid AWS region identifier (e.g. us-east-1)."
  }
}

variable "backup_region" {
  description = "Secondary AWS region for cross-region backups"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Deployment environment (staging | production)"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "project_name" {
  description = "Project identifier used as prefix for all resource names"
  type        = string
  default     = "forex-trading"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]+[a-z0-9]$", var.project_name))
    error_message = "Project name must be lowercase alphanumeric with hyphens."
  }
}

# ── VPC ────────────────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (EKS nodes)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "database_subnet_cidrs" {
  description = "CIDR blocks for database subnets (RDS, ElastiCache)"
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]
}

# ── EKS ────────────────────────────────────────────────────────────────────────
variable "eks_kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for EKS worker nodes"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "eks_node_min_size" {
  description = "Minimum number of EKS worker nodes"
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "Maximum number of EKS worker nodes"
  type        = number
  default     = 10
}

variable "eks_node_desired_size" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 3
}

variable "eks_node_disk_size" {
  description = "EBS volume size (GB) for EKS worker nodes"
  type        = number
  default     = 50
}

# ── RDS ────────────────────────────────────────────────────────────────────────
variable "rds_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.medium"
}

variable "rds_allocated_storage" {
  description = "Initial storage allocation for RDS (GB)"
  type        = number
  default     = 100
}

variable "rds_max_allocated_storage" {
  description = "Maximum storage autoscaling limit for RDS (GB)"
  type        = number
  default     = 500
}

variable "rds_database_name" {
  description = "Name of the PostgreSQL database"
  type        = string
  default     = "forex_trading"
}

variable "rds_username" {
  description = "RDS master username (stored in Secrets Manager)"
  type        = string
  default     = "forex_admin"
  sensitive   = true
}

variable "rds_backup_retention_days" {
  description = "Number of days to retain automated RDS backups"
  type        = number
  default     = 14
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ deployment for RDS"
  type        = bool
  default     = true
}

# ── ElastiCache ────────────────────────────────────────────────────────────────
variable "elasticache_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "elasticache_num_nodes" {
  description = "Number of ElastiCache nodes"
  type        = number
  default     = 2
}

# ── MSK (Kafka) ────────────────────────────────────────────────────────────────
variable "msk_instance_type" {
  description = "MSK broker instance type"
  type        = string
  default     = "kafka.t3.small"
}

variable "msk_number_of_brokers" {
  description = "Number of MSK broker nodes (must be multiple of number of AZs)"
  type        = number
  default     = 2
}

variable "msk_storage_size" {
  description = "Storage size per MSK broker (GB)"
  type        = number
  default     = 100
}

variable "msk_kafka_version" {
  description = "Apache Kafka version for MSK"
  type        = string
  default     = "3.6.0"
}

# ── ECR ────────────────────────────────────────────────────────────────────────
variable "ecr_image_retention_count" {
  description = "Number of images to retain in each ECR repository"
  type        = number
  default     = 10
}

# ── Alerting ───────────────────────────────────────────────────────────────────
variable "alert_email" {
  description = "Email address for CloudWatch/SNS alerts"
  type        = string
  default     = ""
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for deployment notifications"
  type        = string
  default     = ""
  sensitive   = true
}
