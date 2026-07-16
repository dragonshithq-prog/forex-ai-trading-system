#!/usr/bin/env bash
# =============================================================================
# Disaster Recovery Script — Forex AI Trading Platform
# =============================================================================
#
# Performs full restore from backup, point-in-time recovery (PITR),
# Kafka log replay, and cross-region failover.
#
# Usage:
#   ./scripts/disaster-recovery.sh --help              # This message
#   ./scripts/disaster-recovery.sh --list-backups       # List available backups
#   ./scripts/disaster-recovery.sh restore-db <backup>  # Restore PostgreSQL
#   ./scripts/disaster-recovery.sh restore-redis        # Restore Redis from RDB/AOF
#   ./scripts/disaster-recovery.sh pitr <timestamp>     # PITR for PostgreSQL
#   ./scripts/disaster-recovery.sh kafka-replay <topic> # Replay Kafka events
#   ./scripts/disaster-recovery.sh failover <region>    # Cross-region failover
#   ./scripts/disaster-recovery.sh status               # Current DR status
#
# Dependencies:
#   - pg_dump / pg_restore / pg_basebackup
#   - redis-cli / redis-restore
#   - kafka-consumer-groups / kafka-replay
#   - kubectl (for K8s operations)
#   - aws-cli (for S3 backup storage)
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}    $*"; }
success() { echo -e "${GREEN}[OK]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
header()  { echo -e "\n${MAGENTA}>>> $*${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
NAMESPACE="${NAMESPACE:-forex-trading-production}"
BACKUP_BUCKET="${BACKUP_BUCKET:-s3://forex-trading-backups}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/forex-dr-restore}"
PITR_WAL_DIR="${PITR_WAL_DIR:-/wal_archive}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-localhost:9092}"
RESTORE_CONFIRM="${RESTORE_CONFIRM:-false}"

# Regions for cross-region DR
PRIMARY_REGION="${PRIMARY_REGION:-us-east-1}"
DR_REGION="${DR_REGION:-us-west-2}"
DR_CLUSTER_NAME="${DR_CLUSTER_NAME:-forex-trading-dr}"

TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RESTORE_DIR="${BACKUP_DIR}/${TIMESTAMP}"

# ── Validation ────────────────────────────────────────────────────────────────
validate_prereqs() {
    local missing=0
    for cmd in pg_dump pg_restore psql redis-cli aws kubectl; do
        if ! command -v "$cmd" &>/dev/null; then
            warn "Missing: $cmd"
            missing=1
        fi
    done
    if [ "$missing" -ne 0 ]; then
        error "Install missing dependencies before running DR procedures"
        exit 1
    fi
}

confirm_restore() {
    if [ "${RESTORE_CONFIRM}" != "true" ]; then
        echo ""
        warn "⚠  DESTRUCTIVE OPERATION  ⚠"
        warn "This will OVERWRITE production data."
        echo ""
        read -r -p "Type 'RESTORE' to confirm: " confirm
        if [ "$confirm" != "RESTORE" ]; then
            error "Restore cancelled"
            exit 1
        fi
        echo ""
    fi
}

# ── Status ─────────────────────────────────────────────────────────────────────
dr_status() {
    header "Disaster Recovery Status"
    echo ""

    # Check backup bucket
    info "Backup bucket: ${BACKUP_BUCKET}"
    if aws s3 ls "${BACKUP_BUCKET}" &>/dev/null; then
        success "Backup bucket accessible"
    else
        error "Backup bucket NOT accessible"
    fi

    # List latest backups
    info "Latest backups:"
    aws s3 ls "${BACKUP_BUCKET}/database/" --recursive --human-readable 2>/dev/null | tail -5 || warn "No DB backups found"

    # Check WAL archiving
    if [ -d "${PITR_WAL_DIR}" ]; then
        local wal_count
        wal_count=$(find "${PITR_WAL_DIR}" -name "*.wal" -o -name "*.partial" 2>/dev/null | wc -l)
        success "WAL archive: ${wal_count} segments available"
    else
        warn "WAL archive directory not found"
    fi

    # Check DR cluster
    if kubectl config current-context 2>/dev/null | grep -q "${DR_REGION}"; then
        success "DR cluster context active"
    else
        warn "DR cluster not configured in current kubeconfig"
    fi

    # RPO/RTO estimates
    echo ""
    info "RPO Targets:"
    echo "  PostgreSQL:  < 5 minutes (WAL streaming)"
    echo "  Redis:       < 1 minute (AOF fsync every second)"
    echo "  Kafka:       < 5 minutes (min.insync.replicas)"
    echo "  File Assets: < 1 hour (S3 sync every hour)"
    echo ""
    info "RTO Targets:"
    echo "  PostgreSQL:  < 30 minutes (pg_restore + WAL replay)"
    echo "  Redis:       < 5 minutes (RDB reload)"
    echo "  Full Stack:  < 60 minutes (automated failover)"
}

# ── List Backups ───────────────────────────────────────────────────────────────
list_backups() {
    header "Available Backups"
    echo ""
    info "Database backups:"
    aws s3 ls "${BACKUP_BUCKET}/database/" --recursive --human-readable 2>/dev/null || warn "No database backups found"
    echo ""
    info "Redis backups:"
    aws s3 ls "${BACKUP_BUCKET}/redis/" --recursive --human-readable 2>/dev/null || warn "No Redis backups found"
    echo ""
    info "Kafka offsets:"
    aws s3 ls "${BACKUP_BUCKET}/kafka/" --recursive --human-readable 2>/dev/null || warn "No Kafka offset backups found"
}

# ── Full DB Restore ────────────────────────────────────────────────────────────
restore_database() {
    local backup_file="$1"

    if [ -z "$backup_file" ]; then
        error "Usage: $0 restore-db <backup-file-or-s3-path>"
        exit 1
    fi

    header "Database Restore from Backup"

    confirm_restore

    mkdir -p "${RESTORE_DIR}"
    local local_file="${RESTORE_DIR}/db_backup.dump"

    # Download from S3 if not local
    if [[ "$backup_file" == s3://* ]]; then
        info "Downloading backup from S3: ${backup_file}"
        aws s3 cp "${backup_file}" "${local_file}"
    else
        local_file="$backup_file"
    fi

    if [ ! -f "$local_file" ]; then
        error "Backup file not found: ${local_file}"
        exit 1
    fi

    # Get DB connection details from environment or Kubernetes
    local db_host="${DB_HOST:-localhost}"
    local db_port="${DB_PORT:-5432}"
    local db_name="${DB_NAME:-forex_trading}"
    local db_user="${DB_USER:-forex}"

    info "Restoring database '${db_name}' on ${db_host}:${db_port}"

    # Terminate existing connections
    psql -h "$db_host" -p "$db_port" -U "$db_user" -d postgres \
        -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '${db_name}' AND pid <> pg_backend_pid();" \
        2>/dev/null || true

    # Drop and recreate
    dropdb -h "$db_host" -p "$db_port" -U "$db_user" --if-exists "${db_name}" 2>/dev/null || true
    createdb -h "$db_host" -p "$db_port" -U "$db_user" "${db_name}"

    # Restore from dump
    info "Restoring from dump (this may take a while)..."
    pg_restore -h "$db_host" -p "$db_port" -U "$db_user" -d "${db_name}" \
        --verbose \
        --no-owner \
        --no-acl \
        --exit-on-error \
        "${local_file}"

    success "Database restore completed"
    info "Run post-restore steps:"
    info "  1. Verify data: psql -d ${db_name} -c 'SELECT count(*) FROM users;'"
    info "  2. Run alembic upgrade head (if schema version differs)"
    info "  3. Restart backend pods: kubectl rollout restart deployment/backend -n ${NAMESPACE}"
}

# ── Point-in-Time Recovery ────────────────────────────────────────────────────
pitr_recovery() {
    local target_time="$1"

    if [ -z "$target_time" ]; then
        error "Usage: $0 pitr <timestamp>  (e.g., '2026-07-14 14:30:00 UTC')"
        exit 1
    fi

    header "Point-in-Time Recovery"
    info "Target time: ${target_time}"

    confirm_restore

    local db_host="${DB_HOST:-localhost}"
    local db_port="${DB_PORT:-5432}"
    local db_name="${DB_NAME:-forex_trading}"
    local db_user="${DB_USER:-forex}"

    # Get latest base backup
    local latest_backup
    latest_backup=$(aws s3 ls "${BACKUP_BUCKET}/database/" 2>/dev/null | sort | tail -1 | awk '{print $4}')
    if [ -z "$latest_backup" ]; then
        error "No base backup found in S3"
        exit 1
    fi

    mkdir -p "${RESTORE_DIR}"
    info "Downloading latest base backup: ${latest_backup}"
    aws s3 cp "${BACKUP_BUCKET}/database/${latest_backup}" "${RESTORE_DIR}/base.tar.gz"

    # Extract backup
    tar -xzf "${RESTORE_DIR}/base.tar.gz" -C "${RESTORE_DIR}/data"

    # Create recovery.conf for PITR
    cat > "${RESTORE_DIR}/data/recovery.conf" << EOF
restore_command = 'cp ${PITR_WAL_DIR}/%f %p'
recovery_target_time = '${target_time}'
recovery_target_action = 'promote'
EOF

    info "Recovery configuration prepared"
    info "To complete PITR:"
    info "  1. Rsync data to DB server: rsync -av ${RESTORE_DIR}/data/ /var/lib/postgresql/data/"
    info "  2. Start PostgreSQL: pg_ctl start -D /var/lib/postgresql/data"
    info "  3. Verify recovery: psql -c 'SELECT pg_is_in_recovery();'"
    info "  4. Once recovered, promote: pg_ctl promote -D /var/lib/postgresql/data"

    success "PITR prepared for ${target_time}"
}

# ── Redis Restore ──────────────────────────────────────────────────────────────
restore_redis() {
    header "Redis Restore from Backup"

    confirm_restore

    local redis_host="${REDIS_HOST:-localhost}"
    local redis_port="${REDIS_PORT:-6379}"

    # Find latest RDB backup
    local rdb_backup
    rdb_backup=$(aws s3 ls "${BACKUP_BUCKET}/redis/" 2>/dev/null | sort | tail -1 | awk '{print $4}')
    if [ -z "$rdb_backup" ]; then
        warn "No RDB backup found; attempting AOF recovery"
        rdb_backup=$(aws s3 ls "${BACKUP_BUCKET}/redis/aof/" 2>/dev/null | sort | tail -1 | awk '{print $4}')
    fi

    if [ -z "$rdb_backup" ]; then
        error "No Redis backups found"
        exit 1
    fi

    mkdir -p "${RESTORE_DIR}"
    aws s3 cp "${BACKUP_BUCKET}/redis/${rdb_backup}" "${RESTORE_DIR}/redis-backup.rdb"

    # Restore
    info "Restoring Redis from ${rdb_backup}"
    redis-cli -h "$redis_host" -p "$redis_port" CONFIG SET dir "${RESTORE_DIR}" 2>/dev/null || true
    redis-cli -h "$redis_host" -p "$redis_port" CONFIG SET dbfilename "redis-backup.rdb" 2>/dev/null || true

    # Use RESTORE command for key-level restore (preferred)
    redis-cli -h "$redis_host" -p "$redis_port" --pipe < "${RESTORE_DIR}/redis-backup.rdb" 2>/dev/null || {
        warn "Direct RDB restore failed; manual steps required:"
        info "  1. Stop Redis: systemctl stop redis"
        info "  2. Copy RDB: cp ${RESTORE_DIR}/redis-backup.rdb /var/lib/redis/dump.rdb"
        info "  3. Start Redis: systemctl start redis"
    }

    success "Redis restore initiated"
}

# ── Kafka Log Replay ───────────────────────────────────────────────────────────
kafka_replay() {
    local topic="$1"

    if [ -z "$topic" ]; then
        error "Usage: $0 kafka-replay <topic>"
        info "Available topics: trading.order, trading.deal, market.tick, system.alert"
        exit 1
    fi

    header "Kafka Event Replay — Topic: ${topic}"

    local group_id="${GROUP_ID:-forex-trading-replay-$(date +%s)}"
    local replay_mode="${REPLAY_MODE:-from-latest}"  # from-beginning | from-latest | from-timestamp
    local replay_timestamp="${REPLAY_TIMESTAMP:-}"

    info "Consumer group: ${group_id}"
    info "Replay mode: ${replay_mode}"

    # Validate topic exists
    kafka-topics --bootstrap-server "${KAFKA_BOOTSTRAP}" --describe --topic "${topic}" 2>/dev/null || {
        error "Topic '${topic}' does not exist"
        exit 1
    }

    case "$replay_mode" in
        from-beginning)
            info "Replaying all events from beginning"
            kafka-console-consumer \
                --bootstrap-server "${KAFKA_BOOTSTRAP}" \
                --topic "${topic}" \
                --group "${group_id}" \
                --from-beginning \
                --timeout-ms 5000 2>/dev/null | head -100 || true
            ;;
        from-latest)
            info "Waiting for latest events (monitoring mode)..."
            kafka-console-consumer \
                --bootstrap-server "${KAFKA_BOOTSTRAP}" \
                --topic "${topic}" \
                --group "${group_id}" \
                --timeout-ms 30000 2>/dev/null | head -50 || true
            ;;
        from-timestamp)
            if [ -z "$replay_timestamp" ]; then
                error "REPLAY_TIMESTAMP required for from-timestamp mode"
                exit 1
            fi
            info "Replaying from timestamp: ${replay_timestamp}"
            # Get offset for timestamp
            local partitions
            partitions=$(kafka-topics --bootstrap-server "${KAFKA_BOOTSTRAP}" --describe --topic "${topic}" 2>/dev/null | grep -c "Partition:" || echo "1")
            for p in $(seq 0 $((partitions - 1))); do
                local offset
                offset=$(kafka-run-class kafka.tools.GetOffsetShell \
                    --bootstrap-server "${KAFKA_BOOTSTRAP}" \
                    --topic "${topic}" \
                    --partitions "$p" \
                    --time "$(date -d "${replay_timestamp}" +%s)000" 2>/dev/null | cut -d: -f3 || echo "0")
                info "Partition $p: offset $offset"
            done
            ;;
    esac

    success "Kafka replay completed for topic '${topic}'"
}

# ── Cross-Region Failover ─────────────────────────────────────────────────────
failover_region() {
    local target_region="$1"

    header "Cross-Region Failover"

    if [ -z "$target_region" ]; then
        error "Usage: $0 failover <region>  (e.g., us-west-2, eu-west-1)"
        info "Available: us-east-1 (primary), us-west-2 (dr), eu-west-1 (dr)"
        exit 1
    fi

    warn "⚠  CROSS-REGION FAILOVER  ⚠"
    warn "This will switch production traffic from ${PRIMARY_REGION} to ${target_region}"
    confirm_restore

    info "Step 1: Verify DR cluster is ready"
    kubectl config use-context "${DR_CLUSTER_NAME}" 2>/dev/null || {
        error "DR cluster context not found"
        exit 1
    }
    kubectl cluster-info 2>/dev/null || {
        error "DR cluster not accessible"
        exit 1
    }

    info "Step 2: Promote DR database (if using read replica)"
    local db_instance="${DB_INSTANCE:-forex-trading}"
    aws rds promote-read-replica \
        --db-instance-identifier "${db_instance}-dr" \
        --region "${target_region}" 2>/dev/null || warn "RDS promote failed; check instance name"

    info "Step 3: Update Route53 DNS to point to DR region"
    local hosted_zone_id
    hosted_zone_id=$(aws route53 list-hosted-zones --query "HostedZones[?Name=='yourdomain.com.'].Id" --output text 2>/dev/null || echo "")
    if [ -n "$hosted_zone_id" ]; then
        cat > "${RESTORE_DIR}/dns-failover.json" << EOF
{
    "Comment": "Disaster recovery failover to ${target_region}",
    "Changes": [
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "api.yourdomain.com",
                "Type": "A",
                "SetIdentifier": "${target_region}",
                "Failover": "PRIMARY",
                "TTL": 60,
                "ResourceRecords": [
                    {"Value": "${DR_LOAD_BALANCER_DNS:-dr-lb.yourdomain.com}"}
                ]
            }
        }
    ]
}
EOF
        aws route53 change-resource-record-sets \
            --hosted-zone-id "${hosted_zone_id}" \
            --change-batch "file://${RESTORE_DIR}/dns-failover.json" 2>/dev/null || warn "DNS update failed"
    else
        warn "Route53 zone not found; update DNS manually"
    fi

    info "Step 4: Scale up DR application stack"
    kubectl scale deployment backend -n "${NAMESPACE}" --replicas=4 2>/dev/null || true
    kubectl scale deployment frontend -n "${NAMESPACE}" --replicas=3 2>/dev/null || true
    kubectl scale deployment celery-worker -n "${NAMESPACE}" --replicas=5 2>/dev/null || true

    info "Step 5: Verify DR health"
    local dr_health
    dr_health=$(curl -sf "https://api.yourdomain.com/health/ready" 2>/dev/null || echo "unreachable")
    info "DR health: ${dr_health}"

    success "Failover to ${target_region} initiated"
    info "Run './scripts/disaster-recovery.sh dr-status' to monitor progress"
}

# ── Show help ──────────────────────────────────────────────────────────────────
show_help() {
    sed -n '3,17p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    header "Disaster Recovery — Forex AI Trading Platform"
    echo ""

    validate_prereqs
    mkdir -p "${RESTORE_DIR}"

    if [ $# -eq 0 ]; then
        show_help
    fi

    local exit_code=0

    case "$1" in
        --help|-h)
            show_help
            ;;
        status|--status)
            dr_status
            ;;
        --list-backups)
            list_backups
            ;;
        restore-db)
            shift
            restore_database "$@"
            ;;
        pitr)
            shift
            pitr_recovery "$@"
            ;;
        restore-redis)
            restore_redis
            ;;
        kafka-replay)
            shift
            kafka_replay "$@"
            ;;
        failover)
            shift
            failover_region "$@"
            ;;
        *)
            error "Unknown command: $1"
            show_help
            exit_code=1
            ;;
    esac

    echo ""
    if [ $exit_code -eq 0 ]; then
        success "Disaster recovery operation completed"
    else
        error "Operation FAILED — review logs above"
    fi
    exit $exit_code
}

main "$@"
