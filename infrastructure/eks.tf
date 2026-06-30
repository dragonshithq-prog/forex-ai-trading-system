# =============================================================================
# EKS Cluster — Forex AI Trading Platform
# Kubernetes v1.29, t3.medium node group, min=2 max=10
# =============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.14"

  cluster_name    = "${local.name}-eks"
  cluster_version = var.eks_kubernetes_version

  # ── Networking ─────────────────────────────────────────────────────────────
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # ── API Server Access ──────────────────────────────────────────────────────
  cluster_endpoint_public_access       = true
  cluster_endpoint_private_access      = true
  cluster_endpoint_public_access_cidrs = ["0.0.0.0/0"]  # Restrict to office IPs in prod

  # ── Logging ────────────────────────────────────────────────────────────────
  cluster_enabled_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  # ── Add-ons ────────────────────────────────────────────────────────────────
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent              = true
      service_account_role_arn = module.vpc_cni_irsa.iam_role_arn
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  # ── Managed Node Group ─────────────────────────────────────────────────────
  eks_managed_node_groups = {
    main = {
      name           = "${local.name}-nodes"
      instance_types = var.eks_node_instance_types
      ami_type       = "AL2_x86_64"

      min_size     = var.eks_node_min_size
      max_size     = var.eks_node_max_size
      desired_size = var.eks_node_desired_size

      disk_size = var.eks_node_disk_size

      # Spread nodes across AZs
      subnet_ids = module.vpc.private_subnets

      # ── Node Security ───────────────────────────────────────────────────
      enable_bootstrap_user_data = false

      # IMDSv2 only (prevent SSRF credential theft)
      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"      # IMDSv2 required
        http_put_response_hop_limit = 1
        instance_metadata_tags      = "disabled"
      }

      labels = {
        role        = "worker"
        environment = var.environment
      }

      taints = []

      tags = merge(local.common_tags, {
        "k8s.io/cluster-autoscaler/enabled"                  = "true"
        "k8s.io/cluster-autoscaler/${local.name}-eks"        = "owned"
      })
    }
  }

  # ── Access Entries (replace aws-auth ConfigMap) ────────────────────────────
  enable_cluster_creator_admin_permissions = true

  tags = local.common_tags
}

# ── IRSA: VPC CNI ─────────────────────────────────────────────────────────────
module "vpc_cni_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.39"

  role_name             = "${local.name}-vpc-cni-irsa"
  attach_vpc_cni_policy = true
  vpc_cni_enable_ipv4   = true

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-node"]
    }
  }
}

# ── IRSA: EBS CSI Driver ──────────────────────────────────────────────────────
module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.39"

  role_name             = "${local.name}-ebs-csi-irsa"
  attach_ebs_csi_policy = true

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# ── StorageClass: gp3 (set as default) ────────────────────────────────────────
resource "kubernetes_storage_class" "gp3" {
  metadata {
    name = "gp3"
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Retain"
  allow_volume_expansion = true
  volume_binding_mode    = "WaitForFirstConsumer"

  parameters = {
    type      = "gp3"
    encrypted = "true"
    kmsKeyId  = aws_kms_key.ebs.arn
    iops      = "3000"
    throughput = "125"
  }
}
