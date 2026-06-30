# =============================================================================
# RDS PostgreSQL — Forex AI Trading Platform
# Multi-AZ, encrypted, automated backups, Performance Insights
# =============================================================================

# ── RDS Parameter Group ───────────────────────────────────────────────────────
resource "aws_db_parameter_group" "postgres" {
  name        = "${local.name}-pg16"
  family      = "postgres16"
  description = "Custom parameter group for Forex Trading PostgreSQL 16"

  # TimescaleDB extension support
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_duration"
    value = "0"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"   # Log queries longer than 1 second
  }

  parameter {
    name  = "max_connections"
    value = "200"
  }

  parameter {
    name  = "work_mem"
    value = "65536"   # 64MB in KB
  }

  tags = local.common_tags
}

# ── RDS Subnet Group ──────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name}-rds-subnet-group"
  subnet_ids = module.vpc.database_subnets

  tags = merge(local.common_tags, {
    Name = "${local.name}-rds-subnet-group"
  })
}

# ── RDS Instance ──────────────────────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  identifier = "${local.name}-postgres"

  # Engine
  engine               = "postgres"
  engine_version       = "16.2"
  instance_class       = var.rds_instance_class
  db_name              = var.rds_database_name
  username             = var.rds_username
  password             = random_password.rds_password.result
  parameter_group_name = aws_db_parameter_group.postgres.name

  # Storage
  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_allocated_storage   # Enable autoscaling
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn

  # High Availability
  multi_az = var.rds_multi_az

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # Backups
  backup_retention_period   = var.rds_backup_retention_days
  backup_window             = "02:00-03:00"               # UTC
  maintenance_window        = "sun:04:00-sun:05:00"       # UTC
  delete_automated_backups  = false
  copy_tags_to_snapshot     = true
  final_snapshot_identifier = "${local.name}-postgres-final-snapshot"
  skip_final_snapshot       = var.environment == "staging"

  # Performance & Monitoring
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  monitoring_interval                   = 60
  monitoring_role_arn                   = aws_iam_role.rds_monitoring.arn
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]

  # Deletion Protection
  deletion_protection = var.environment == "production"

  # Auto minor version upgrade
  auto_minor_version_upgrade = true
  apply_immediately          = var.environment == "staging"

  tags = merge(local.common_tags, {
    Name = "${local.name}-postgres"
  })
}

# ── Random Password ────────────────────────────────────────────────────────────
resource "random_password" "rds_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# ── RDS Read Replica (production only) ────────────────────────────────────────
resource "aws_db_instance" "postgres_replica" {
  count = var.environment == "production" ? 1 : 0

  identifier             = "${local.name}-postgres-replica"
  replicate_source_db    = aws_db_instance.postgres.identifier
  instance_class         = var.rds_instance_class
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.rds.arn
  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.rds.id]

  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn

  auto_minor_version_upgrade = true
  skip_final_snapshot        = true

  tags = merge(local.common_tags, {
    Name = "${local.name}-postgres-replica"
    Role = "read-replica"
  })
}
