# =============================================================================
# Security Groups — Forex AI Trading Platform
# =============================================================================

# ── EKS Nodes Security Group ──────────────────────────────────────────────────
resource "aws_security_group" "eks_nodes" {
  name        = "${local.name}-eks-nodes"
  description = "Security group for EKS worker nodes"
  vpc_id      = module.vpc.vpc_id

  # Allow all egress (nodes need internet for pulling images, AWS APIs)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  # Allow nodes to communicate with each other
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
    description = "Node-to-node communication"
  }

  # Allow EKS control plane to reach nodes
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
    description     = "EKS control plane to nodes"
  }

  ingress {
    from_port       = 10250
    to_port         = 10250
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
    description     = "Kubelet API"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name}-eks-nodes"
    "kubernetes.io/cluster/${local.name}-eks" = "owned"
  })
}

# ── RDS Security Group ────────────────────────────────────────────────────────
resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "Security group for RDS PostgreSQL — allow only EKS nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "PostgreSQL from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = merge(local.common_tags, { Name = "${local.name}-rds" })
}

# ── ElastiCache Security Group ────────────────────────────────────────────────
resource "aws_security_group" "elasticache" {
  name        = "${local.name}-elasticache"
  description = "Security group for ElastiCache Redis — allow only EKS nodes"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "Redis from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name}-elasticache" })
}

# ── MSK Security Group ────────────────────────────────────────────────────────
resource "aws_security_group" "msk" {
  name        = "${local.name}-msk"
  description = "Security group for MSK Kafka brokers"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "Kafka PLAINTEXT from EKS"
  }

  ingress {
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "Kafka TLS from EKS"
  }

  ingress {
    from_port       = 9198
    to_port         = 9198
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "JMX Exporter (Prometheus)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name}-msk" })
}

# ── VPC Endpoints Security Group ──────────────────────────────────────────────
resource "aws_security_group" "vpc_endpoints" {
  name        = "${local.name}-vpc-endpoints"
  description = "Security group for VPC Interface Endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "HTTPS from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${local.name}-vpc-endpoints" })
}
