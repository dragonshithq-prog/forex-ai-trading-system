# =============================================================================
# ElastiCache Redis — Forex AI Trading Platform
# Cluster mode, multi-AZ, encrypted at rest and in transit
# =============================================================================

# ── ElastiCache Subnet Group ──────────────────────────────────────────────────
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.name}-redis-subnet-group"
  subnet_ids = module.vpc.database_subnets

  tags = merge(local.common_tags, {
    Name = "${local.name}-redis-subnet-group"
  })
}

# ── ElastiCache Parameter Group ───────────────────────────────────────────────
resource "aws_elasticache_parameter_group" "redis" {
  name        = "${local.name}-redis7"
  family      = "redis7"
  description = "Custom Redis 7 parameter group for Forex Trading"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  parameter {
    name  = "timeout"
    value = "300"
  }

  parameter {
    name  = "tcp-keepalive"
    value = "300"
  }

  parameter {
    name  = "activerehashing"
    value = "yes"
  }

  tags = local.common_tags
}

# ── Random auth token ─────────────────────────────────────────────────────────
resource "random_password" "redis_auth_token" {
  length  = 64
  special = false   # ElastiCache auth tokens must be alphanumeric
}

# ── ElastiCache Replication Group (Redis) ─────────────────────────────────────
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name}-redis"
  description          = "Redis cluster for Forex AI Trading Platform"

  # Engine
  engine               = "redis"
  engine_version       = "7.2"
  node_type            = var.elasticache_node_type
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  port                 = 6379

  # Cluster
  num_cache_clusters = var.elasticache_num_nodes
  automatic_failover_enabled = var.elasticache_num_nodes > 1 ? true : false
  multi_az_enabled           = var.elasticache_num_nodes > 1 ? true : false

  # Networking
  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.elasticache.id]

  # Security
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.elasticache.arn
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth_token.result

  # Maintenance and Backups
  maintenance_window         = "sun:05:00-sun:06:00"
  snapshot_window            = "03:00-04:00"
  snapshot_retention_limit   = 7

  # Auto failover
  apply_immediately = var.environment == "staging"

  tags = merge(local.common_tags, {
    Name = "${local.name}-redis"
  })
}
