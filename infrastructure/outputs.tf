# =============================================================================
# Terraform Outputs — Forex AI Trading Platform
# =============================================================================

# ── Identity ───────────────────────────────────────────────────────────────────
output "account_id" {
  description = "AWS Account ID"
  value       = local.account_id
}

output "region" {
  description = "AWS Region"
  value       = local.region
}

# ── VPC ────────────────────────────────────────────────────────────────────────
output "vpc_id" {
  description = "ID of the main VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnets
}

output "private_subnet_ids" {
  description = "IDs of private subnets (EKS nodes)"
  value       = module.vpc.private_subnets
}

output "database_subnet_ids" {
  description = "IDs of database subnets"
  value       = module.vpc.database_subnets
}

# ── EKS ────────────────────────────────────────────────────────────────────────
output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "API server endpoint for the EKS cluster"
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "eks_cluster_ca_certificate" {
  description = "Base64-encoded certificate authority for the EKS cluster"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "eks_node_group_arn" {
  description = "ARN of the EKS managed node group"
  value       = module.eks.eks_managed_node_groups["main"].node_group_arn
}

output "kubeconfig_command" {
  description = "Command to update kubeconfig for kubectl access"
  value       = "aws eks update-kubeconfig --region ${local.region} --name ${module.eks.cluster_name}"
}

# ── RDS ────────────────────────────────────────────────────────────────────────
output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (writer)"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = true
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.postgres.db_name
}

output "rds_secret_arn" {
  description = "ARN of the Secrets Manager secret containing RDS credentials"
  value       = aws_secretsmanager_secret.rds_credentials.arn
}

# ── ElastiCache ────────────────────────────────────────────────────────────────
output "elasticache_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive   = true
}

output "elasticache_port" {
  description = "ElastiCache Redis port"
  value       = aws_elasticache_replication_group.redis.port
}

# ── MSK ────────────────────────────────────────────────────────────────────────
output "msk_bootstrap_brokers" {
  description = "MSK Kafka bootstrap broker string"
  value       = aws_msk_cluster.kafka.bootstrap_brokers_tls
  sensitive   = true
}

output "msk_zookeeper_connect" {
  description = "MSK Zookeeper connection string (for legacy tools)"
  value       = aws_msk_cluster.kafka.zookeeper_connect_string
  sensitive   = true
}

# ── ECR ────────────────────────────────────────────────────────────────────────
output "ecr_backend_repository_url" {
  description = "ECR repository URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_repository_url" {
  description = "ECR repository URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecr_login_command" {
  description = "Command to authenticate Docker with ECR"
  value       = "aws ecr get-login-password --region ${local.region} | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${local.region}.amazonaws.com"
}

# ── IAM ────────────────────────────────────────────────────────────────────────
output "eks_node_role_arn" {
  description = "IAM role ARN for EKS worker nodes"
  value       = aws_iam_role.eks_node_role.arn
}

output "backend_irsa_role_arn" {
  description = "IAM role ARN for backend service account (IRSA)"
  value       = aws_iam_role.backend_irsa.arn
}

# ── Secrets Manager ────────────────────────────────────────────────────────────
output "app_secrets_arn" {
  description = "ARN of the Secrets Manager secret containing application credentials"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

# ── Summary ────────────────────────────────────────────────────────────────────
output "deployment_summary" {
  description = "High-level deployment summary"
  value = {
    environment    = var.environment
    region         = local.region
    eks_cluster    = module.eks.cluster_name
    rds_endpoint   = aws_db_instance.postgres.endpoint
    ecr_backend    = aws_ecr_repository.backend.repository_url
    ecr_frontend   = aws_ecr_repository.frontend.repository_url
  }
  sensitive = true
}
