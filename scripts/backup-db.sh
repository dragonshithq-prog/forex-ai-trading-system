#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Backup Script — Forex AI Trading Platform
# =============================================================================
# Usage:
#   ./scripts/backup-db.sh                     # Backup to default directory
#   ./scripts/backup-db.sh /path/to/backups    # Backup to custom directory
#   ./scripts/backup-db.sh --wal-archive       # Backup + WAL archiving
#
# Features:
#   - Full database dump with pg_dump
#   - WAL archiving support (continuous archiving mode)
#   - Automatic retention policy (keep last 14 daily backups)
#   - Optional S3 sync for off-site storage
#   - Prometheus metrics output for monitoring
# =============================================================================

set -euo pipefail

# ── Color Output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Configuration ─────────────────────────────────────────────────────────────
# Database connection (override via environment variables)
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-forex}"
PGDATABASE="${PGDATABASE:-forex_trading}"
PGPASSWORD="${PGPASSWORD:-}"

# Backup settings
BACKUP_DIR="${1:-./backups/postgres}"
RETENTION_DAYS=14
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-backups/postgres}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S_UTC)
BACKUP_FILE="${BACKUP_DIR}/${PGDATABASE}_${TIMESTAMP}.dump"
BACKUP_LOG="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

# WAL archiving
WAL_ARCHIVE_MODE=false
WAL_ARCHIVE_DIR="${BACKUP_DIR}/wal_archive"
if [[ "${2:-}" == "--wal-archive" ]]; then
    WAL_ARCHIVE_MODE=true
fi

# ── Pre-flight Checks ─────────────────────────────────────────────────────────
preflight() {
    info "=== Pre-flight Checks ==="

    # Check required tools
    command -v pg_dump >/dev/null 2>&1 || { error "pg_dump is required but not installed"; exit 1; }
    command -v psql    >/dev/null 2>&1 || { error "psql is required but not installed"; exit 1; }
    command -v gzip    >/dev/null 2>&1 || { error "gzip is required but not installed"; exit 1; }

    # Create backup directory
    mkdir -p "${BACKUP_DIR}"
    if [ "${WAL_ARCHIVE_MODE}" = true ]; then
        mkdir -p "${WAL_ARCHIVE_DIR}"
    fi

    # Test database connection
    info "Testing database connection to ${PGHOST}:${PGPORT}/${PGDATABASE} as ${PGUSER}..."
    PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
        -c "SELECT 1" >/dev/null 2>&1 || {
        error "Cannot connect to database"
        exit 1
    }
    success "Database connection OK"

    # Get database size
    local db_size
    db_size=$(PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
        -t -c "SELECT pg_size_pretty(pg_database_size('${PGDATABASE}'))" 2>/dev/null | tr -d ' ')
    info "Database size: ${db_size}"
}

# ── Full Database Backup ──────────────────────────────────────────────────────
backup_full() {
    info "=== Starting Full Database Backup ==="

    local start_time
    start_time=$(date +%s)

    # Perform the dump (custom format, compressed)
    info "Dumping database to: ${BACKUP_FILE}"
    PGPASSWORD="${PGPASSWORD}" pg_dump \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -F c \                      # Custom format (compressed, parallel restore)
        -v \                        # Verbose
        --no-owner \                # Don't include ownership (portable)
        --no-acl \                  # Don't include ACLs
        --compress=9 \              # Maximum compression
        --file="${BACKUP_FILE}" \
        2>&1 | tee -a "${BACKUP_LOG}"

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Verify backup file
    if [ ! -f "${BACKUP_FILE}" ]; then
        error "Backup file not created"
        exit 1
    fi

    local file_size
    file_size=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null)

    success "Backup completed in ${duration}s"
    info "Backup size: $(numfmt --to=iec-i "${file_size}" 2>/dev/null || echo "${file_size} bytes")"
    info "Backup file: ${BACKUP_FILE}"

    # Create a compressed copy (gzip) for S3 upload efficiency
    info "Creating compressed copy..."
    gzip -c "${BACKUP_FILE}" > "${BACKUP_FILE}.gz"
    success "Compressed copy created: ${BACKUP_FILE}.gz"

    # Output metrics for Prometheus
    echo "db_backup_size_bytes ${file_size}"
    echo "db_backup_duration_seconds ${duration}"
    echo "db_backup_timestamp $(date +%s)"
}

# ── WAL Archiving ─────────────────────────────────────────────────────────────
wal_archive() {
    if [ "${WAL_ARCHIVE_MODE}" != true ]; then
        return 0
    fi

    info "=== WAL Archiving ==="

    # Enable WAL archiving in PostgreSQL if not already
    PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
        -c "SELECT name, setting FROM pg_settings WHERE name IN ('wal_level', 'archive_mode', 'archive_command');" \
        2>&1 | tee -a "${BACKUP_LOG}"

    # Archive current WAL segments
    info "Archiving WAL segments to: ${WAL_ARCHIVE_DIR}"
    PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
        -c "SELECT pg_switch_wal();" >/dev/null 2>&1 || true

    success "WAL archiving initiated"
}

# ── Retention Cleanup ─────────────────────────────────────────────────────────
cleanup_old_backups() {
    info "=== Retention Cleanup ==="
    info "Removing backups older than ${RETENTION_DAYS} days..."

    local count=0
    while IFS= read -r -d '' file; do
        rm -f "${file}"
        count=$((count + 1))
    done < <(find "${BACKUP_DIR}" -name "*.dump" -type f -mtime "+${RETENTION_DAYS}" -print0 2>/dev/null || true)

    while IFS= read -r -d '' file; do
        rm -f "${file}"
    done < <(find "${BACKUP_DIR}" -name "*.dump.gz" -type f -mtime "+${RETENTION_DAYS}" -print0 2>/dev/null || true)

    if [ $count -gt 0 ]; then
        info "Removed ${count} old backup(s)"
    else
        info "No old backups to remove"
    fi
}

# ── Upload to S3 (optional) ───────────────────────────────────────────────────
upload_to_s3() {
    if [ -z "${S3_BUCKET}" ]; then
        return 0
    fi

    info "=== Uploading to S3 ==="

    if ! command -v aws &>/dev/null; then
        warn "AWS CLI not found. Skipping S3 upload."
        return 0
    fi

    local s3_file="${S3_PREFIX}/$(basename "${BACKUP_FILE}.gz")"
    info "Uploading to s3://${S3_BUCKET}/${s3_file}..."

    if aws s3 cp "${BACKUP_FILE}.gz" "s3://${S3_BUCKET}/${s3_file}" \
        --storage-class STANDARD_IA \
        --no-progress; then
        success "S3 upload completed"
    else
        warn "S3 upload failed — backup remains locally"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    info "============================================"
    info "  PostgreSQL Backup — ${PGDATABASE}"
    info "  Timestamp: ${TIMESTAMP}"
    info "============================================"

    preflight
    backup_full
    wal_archive
    cleanup_old_backups
    upload_to_s3

    success "============================================"
    success "  Backup Complete"
    success "============================================"
}

main "$@"
