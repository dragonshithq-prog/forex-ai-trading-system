# =============================================================================
# VPC — Forex AI Trading Platform
# 2 public + 2 private + 2 database subnets across 2 AZs
# =============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr

  azs                  = local.azs
  public_subnets       = var.public_subnet_cidrs
  private_subnets      = var.private_subnet_cidrs
  database_subnets     = var.database_subnet_cidrs

  # ── NAT Gateway ────────────────────────────────────────────────────────────
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment == "staging"    # One NAT for staging, one per AZ for prod
  enable_vpn_gateway   = false

  # ── DNS ────────────────────────────────────────────────────────────────────
  enable_dns_hostnames = true
  enable_dns_support   = true

  # ── Database subnet group (required by RDS + ElastiCache) ─────────────────
  create_database_subnet_group       = true
  create_database_subnet_route_table = true

  # ── VPC Flow Logs ──────────────────────────────────────────────────────────
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
  flow_log_max_aggregation_interval    = 60
  flow_log_cloudwatch_log_group_retention_in_days = 30

  # ── Tags for EKS subnet discovery ─────────────────────────────────────────
  public_subnet_tags = {
    "kubernetes.io/cluster/${local.name}-eks" = "shared"
    "kubernetes.io/role/elb"                  = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${local.name}-eks" = "shared"
    "kubernetes.io/role/internal-elb"         = "1"
  }

  tags = local.common_tags
}

# ── VPC Endpoints (reduce NAT Gateway costs + improve security) ───────────────
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat(module.vpc.private_route_table_ids, module.vpc.public_route_table_ids)
  tags              = merge(local.common_tags, { Name = "${local.name}-s3-endpoint" })
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${local.region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  tags                = merge(local.common_tags, { Name = "${local.name}-ecr-api-endpoint" })
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${local.region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  tags                = merge(local.common_tags, { Name = "${local.name}-ecr-dkr-endpoint" })
}

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${local.region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  tags                = merge(local.common_tags, { Name = "${local.name}-secretsmanager-endpoint" })
}
