# =============================================================================
# Amazon MSK (Managed Kafka) — Forex AI Trading Platform
# 2 brokers, kafka.t3.small, TLS encryption, MSK Connect capable
# =============================================================================

# ── MSK Configuration ─────────────────────────────────────────────────────────
resource "aws_msk_configuration" "kafka" {
  name           = "${local.name}-kafka-config"
  kafka_versions = [var.msk_kafka_version]

  server_properties = <<PROPERTIES
auto.create.topics.enable=false
default.replication.factor=2
min.insync.replicas=2
num.partitions=6
num.replica.fetchers=2
replica.lag.time.max.ms=30000
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600
socket.send.buffer.bytes=102400
unclean.leader.election.enable=false
log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000
PROPERTIES
}

# ── MSK Cluster ───────────────────────────────────────────────────────────────
resource "aws_msk_cluster" "kafka" {
  cluster_name           = "${local.name}-kafka"
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = var.msk_number_of_brokers

  broker_node_group_info {
    instance_type   = var.msk_instance_type
    client_subnets  = slice(module.vpc.private_subnets, 0, var.msk_number_of_brokers)
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_storage_size

        provisioned_throughput {
          enabled           = true
          volume_throughput = 250
        }
      }
    }

    connectivity_info {
      public_access {
        type = "DISABLED"
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.kafka.arn
    revision = aws_msk_configuration.kafka.latest_revision
  }

  # ── Encryption ────────────────────────────────────────────────────────────
  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
    encryption_at_rest_kms_key_arn = aws_kms_key.msk.arn
  }

  # ── Client Authentication ──────────────────────────────────────────────────
  client_authentication {
    unauthenticated = false
    sasl {
      iam   = true
      scram = false
    }
    tls {}
  }

  # ── Logging ────────────────────────────────────────────────────────────────
  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
      firehose {
        enabled = false
      }
      s3 {
        enabled = false
      }
    }
  }

  # ── Monitoring ────────────────────────────────────────────────────────────
  open_monitoring {
    prometheus {
      jmx_exporter {
        enabled_in_broker = true
      }
      node_exporter {
        enabled_in_broker = true
      }
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name}-kafka"
  })
}

# ── CloudWatch Log Group for MSK ──────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/${local.name}"
  retention_in_days = 30
  tags              = local.common_tags
}
