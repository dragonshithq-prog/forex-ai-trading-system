# =============================================================================
# Secrets Manager + KMS — Forex AI Trading Platform
# All application credentials stored in Secrets Manager
# KMS keys for encryption at rest
# =============================================================================

# ── KMS Keys ──────────────────────────────────────────────────────────────────

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-rds-kms" })
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${local.name}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

resource "aws_kms_key" "elasticache" {
  description             = "KMS key for ElastiCache encryption — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-elasticache-kms" })
}

resource "aws_kms_alias" "elasticache" {
  name          = "alias/${local.name}-elasticache"
  target_key_id = aws_kms_key.elasticache.key_id
}

resource "aws_kms_key" "msk" {
  description             = "KMS key for MSK encryption — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-msk-kms" })
}

resource "aws_kms_alias" "msk" {
  name          = "alias/${local.name}-msk"
  target_key_id = aws_kms_key.msk.key_id
}

resource "aws_kms_key" "ecr" {
  description             = "KMS key for ECR encryption — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-ecr-kms" })
}

resource "aws_kms_alias" "ecr" {
  name          = "alias/${local.name}-ecr"
  target_key_id = aws_kms_key.ecr.key_id
}

resource "aws_kms_key" "app_secrets" {
  description             = "KMS key for Secrets Manager — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-secrets-kms" })
}

resource "aws_kms_alias" "app_secrets" {
  name          = "alias/${local.name}-secrets"
  target_key_id = aws_kms_key.app_secrets.key_id
}

resource "aws_kms_key" "ebs" {
  description             = "KMS key for EBS volumes — ${local.name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.common_tags, { Name = "${local.name}-ebs-kms" })
}

resource "aws_kms_alias" "ebs" {
  name          = "alias/${local.name}-ebs"
  target_key_id = aws_kms_key.ebs.key_id
}

# ── Secrets Manager: RDS Credentials ─────────────────────────────────────────
resource "aws_secretsmanager_secret" "rds_credentials" {
  name                    = "${local.name}/rds/credentials"
  description             = "RDS PostgreSQL master credentials for ${local.name}"
  kms_key_id              = aws_kms_key.app_secrets.arn
  recovery_window_in_days = 30

  tags = merge(local.common_tags, {
    Name        = "${local.name}-rds-credentials"
    SecretType  = "database"
    RotationDue = "90days"
  })
}

resource "aws_secretsmanager_secret_version" "rds_credentials" {
  secret_id = aws_secretsmanager_secret.rds_credentials.id

  secret_string = jsonencode({
    username             = var.rds_username
    password             = random_password.rds_password.result
    engine               = "postgres"
    host                 = aws_db_instance.postgres.address
    port                 = aws_db_instance.postgres.port
    dbname               = var.rds_database_name
    dbInstanceIdentifier = aws_db_instance.postgres.id
    DATABASE_URL         = "postgresql+asyncpg://${var.rds_username}:${random_password.rds_password.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.rds_database_name}"
  })

  lifecycle {
    ignore_changes = [secret_string]   # Allow rotation without drift
  }
}

# ── Secrets Manager: ElastiCache Auth Token ───────────────────────────────────
resource "aws_secretsmanager_secret" "redis_credentials" {
  name                    = "${local.name}/redis/credentials"
  description             = "ElastiCache Redis auth token for ${local.name}"
  kms_key_id              = aws_kms_key.app_secrets.arn
  recovery_window_in_days = 30
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "redis_credentials" {
  secret_id = aws_secretsmanager_secret.redis_credentials.id

  secret_string = jsonencode({
    auth_token = random_password.redis_auth_token.result
    host       = aws_elasticache_replication_group.redis.primary_endpoint_address
    port       = 6379
    REDIS_URL  = "redis://:${random_password.redis_auth_token.result}@${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Secrets Manager: Application Secrets ──────────────────────────────────────
# JWT keys, AI API keys, broker credentials — set values manually after creation
resource "aws_secretsmanager_secret" "app_secrets" {
  name                    = "${local.name}/app/secrets"
  description             = "Application-level secrets for ${local.name}"
  kms_key_id              = aws_kms_key.app_secrets.arn
  recovery_window_in_days = 30

  tags = merge(local.common_tags, {
    Name       = "${local.name}-app-secrets"
    SecretType = "application"
  })
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id

  # These values must be set manually or via CI/CD after provisioning.
  # Using placeholder values here so Terraform can create the secret structure.
  secret_string = jsonencode({
    JWT_SECRET_KEY           = "REPLACE_ME_jwt_secret_key"
    JWT_REFRESH_SECRET_KEY   = "REPLACE_ME_jwt_refresh_secret_key"
    OANDA_API_KEY            = "REPLACE_ME_oanda_api_key"
    OANDA_ACCOUNT_ID         = "REPLACE_ME_oanda_account_id"
    OPENAI_API_KEY           = "REPLACE_ME_openai_api_key"
    GRAFANA_ADMIN_PASSWORD   = "REPLACE_ME_grafana_admin_password"
    GRAFANA_SECRET_KEY       = "REPLACE_ME_grafana_secret_key"
    SLACK_WEBHOOK_URL        = "REPLACE_ME_slack_webhook_url"
    FLOWER_PASSWORD          = "REPLACE_ME_flower_password"
  })

  lifecycle {
    ignore_changes = [secret_string]   # Prevent Terraform from overwriting manual updates
  }
}

# ── MSK Kafka Cluster ID ──────────────────────────────────────────────────────
resource "random_uuid" "kafka_cluster_id" {}

resource "aws_secretsmanager_secret" "kafka_cluster_id" {
  name                    = "${local.name}/kafka/cluster-id"
  description             = "Kafka KRaft cluster ID for ${local.name}"
  kms_key_id              = aws_kms_key.app_secrets.arn
  recovery_window_in_days = 30
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "kafka_cluster_id" {
  secret_id     = aws_secretsmanager_secret.kafka_cluster_id.id
  secret_string = jsonencode({ KAFKA_CLUSTER_ID = random_uuid.kafka_cluster_id.result })
}
