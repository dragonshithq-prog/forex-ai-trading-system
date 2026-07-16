#!/usr/bin/env bash
# =============================================================================
# Production Configuration Validation — Forex AI Trading Platform
# =============================================================================
#
# Validates all configuration aspects before production deployment:
#   - Environment variables presence and format
#   - PEM certificate formats
#   - Database connectivity
#   - Redis connectivity
#   - Kafka connectivity
#   - Disk space, memory, CPU
#   - Log directory permissions
#   - Secret key strength
#
# Usage:
#   ./scripts/validate-config.sh            # Run all checks
#   ./scripts/validate-config.sh --env      # Environment variables only
#   ./scripts/validate-config.sh --certs    # Certificate validation only
#   ./scripts/validate-config.sh --connect  # Connectivity checks only
#   ./scripts/validate-config.sh --system   # System resources only
#   ./scripts/validate-config.sh --watch    # Watch mode (continuous)
#   ./scripts/validate-config.sh --help     # Show help
#
# Returns: 0 if all checks pass, 1 if any check fails
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}    $*"; }
success() { echo -e "${GREEN}[PASS]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}   $*"; }
error()   { echo -e "${RED}[FAIL]${NC}   $*"; }
header()  { echo -e "\n${MAGENTA}══════════════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}$*${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
SKIP_CONNECTIVITY="${SKIP_CONNECTIVITY:-false}"
SKIP_SYSTEM="${SKIP_SYSTEM:-false}"
STRICT_MODE="${STRICT_MODE:-false}"  # If true, warnings become errors
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# Required environment variables
REQUIRED_ENV_VARS=(
    "SECRET_KEY"
    "JWT_SECRET_KEY"
    "DATABASE_URL"
    "REDIS_URL"
)

# Optional but recommended
RECOMMENDED_ENV_VARS=(
    "JWT_ALGORITHM"
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    "KAFKA_BOOTSTRAP_SERVERS"
    "PROMETHEUS_ENABLED"
    "LOG_LEVEL"
    "LOG_FORMAT"
    "ENVIRONMENT"
)

# ── Help ───────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '3,20p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

# ── Assert Helpers ─────────────────────────────────────────────────────────────
assert_pass() {
    local message="$1"
    echo -e "  ${GREEN}✓${NC} ${message}"
    PASS_COUNT=$((PASS_COUNT + 1))
}

assert_fail() {
    local message="$1"
    echo -e "  ${RED}✗${NC} ${message}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

assert_warn() {
    local message="$1"
    echo -e "  ${YELLOW}⚠${NC} ${message}"
    WARN_COUNT=$((WARN_COUNT + 1))
    if [ "${STRICT_MODE}" = "true" ]; then
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

check_cmd() {
    local cmd="$1"
    command -v "$cmd" &>/dev/null
}

# ── Environment Variable Check ─────────────────────────────────────────────────
validate_env_vars() {
    header "Environment Variables"

    # Load .env if present
    if [ -f ".env" ]; then
        set +a
        source .env 2>/dev/null || true
        set -a
        assert_pass ".env file loaded"
    else
        assert_warn "No .env file found — checking OS environment"
    fi

    # Check required vars
    local all_required=true
    for var in "${REQUIRED_ENV_VARS[@]}"; do
        if [ -z "${!var:-}" ]; then
            assert_fail "REQUIRED: ${var} is not set"
            all_required=false
        else
            local masked
            masked="${!var}"
            if [ ${#masked} -gt 8 ]; then
                masked="${masked:0:4}...${masked: -4}"
            fi
            assert_pass "REQUIRED: ${var} = ${masked}"
        fi
    done

    # Check recommended vars
    for var in "${RECOMMENDED_ENV_VARS[@]}"; do
        if [ -z "${!var:-}" ]; then
            assert_warn "RECOMMENDED: ${var} is not set (using default)"
        else
            assert_pass "RECOMMENDED: ${var} = ${!var}"
        fi
    done

    # Check for placeholder values
    if [ "${SECRET_KEY:-}" = "change-me-in-production" ] || [ "${SECRET_KEY:-}" = "your-secret-key" ]; then
        assert_fail "SECRET_KEY contains placeholder value — CHANGE IT"
    fi

    if [ "${JWT_SECRET_KEY:-}" = "your-jwt-secret-change-in-production" ]; then
        assert_fail "JWT_SECRET_KEY contains placeholder value — CHANGE IT"
    fi

    # Check ENVIRONMENT
    if [ "${ENVIRONMENT:-}" = "development" ] && [ "${STRICT_MODE:-}" = "true" ]; then
        assert_warn "ENVIRONMENT=development in production validation"
    fi

    # Check JWT algorithm
    if [ "${JWT_ALGORITHM:-HS256}" = "HS256" ]; then
        assert_warn "JWT_ALGORITHM=HS256 — consider RS256 for production"
    fi

    # Python path check
    if [ -d ".venv" ] || [ -d ".venv312" ] || [ -d "venv" ]; then
        assert_pass "Python virtual environment found"
    else
        assert_warn "No Python virtual environment found"
    fi
}

# ── Certificate Validation ─────────────────────────────────────────────────────
validate_certificates() {
    header "Certificate Validation"

    local certs_found=false
    local cert_files

    # Common cert locations
    cert_files=$(find . -name "*.pem" -o -name "*.crt" -o -name "*.key" -o -name "*.cert" 2>/dev/null | grep -v ".venv" | grep -v "node_modules" || true)

    if [ -z "$cert_files" ]; then
        assert_warn "No certificate files found — OK if using TLS termination at LB"
        return
    fi

    for cert in $cert_files; do
        if [[ "$cert" == *.pem ]] || [[ "$cert" == *.crt ]]; then
            if check_cmd "openssl"; then
                if openssl x509 -in "$cert" -noout -dates 2>/dev/null; then
                    local expiry
                    expiry=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)
                    assert_pass "Certificate valid: ${cert} (expires: ${expiry})"
                    certs_found=true
                else
                    assert_warn "Invalid certificate: ${cert}"
                fi
            else
                assert_pass "Certificate found: ${cert}"
                certs_found=true
            fi
        elif [[ "$cert" == *.key ]]; then
            # Check private key permissions
            local perms
            perms=$(stat -f "%Lp" "$cert" 2>/dev/null || stat -c "%a" "$cert" 2>/dev/null || echo "???")
            if [ "$perms" = "400" ] || [ "$perms" = "600" ]; then
                assert_pass "Private key permissions OK: ${cert} (${perms})"
            else
                assert_warn "Private key permissions: ${cert} (${perms}) — should be 600"
            fi
            certs_found=true
        fi
    done

    if [ "$certs_found" = false ]; then
        assert_warn "No certificates validated"
    fi
}

# ── Connectivity Checks ────────────────────────────────────────────────────────
check_connectivity() {
    header "Service Connectivity"

    if [ "${SKIP_CONNECTIVITY}" = "true" ]; then
        assert_warn "Connectivity checks skipped (SKIP_CONNECTIVITY=true)"
        return
    fi

    # Database
    local db_url="${DATABASE_URL:-}"
    if [ -n "$db_url" ]; then
        info "Testing database connectivity..."
        if check_cmd "psql" && [[ "$db_url" == postgresql* ]]; then
            if psql "$db_url" -c "SELECT 1" &>/dev/null; then
                assert_pass "PostgreSQL connection OK"
            else
                assert_fail "PostgreSQL connection FAILED"
            fi
        elif [[ "$db_url" == sqlite* ]]; then
            # SQLite — check file exists
            local db_path
            db_path=$(echo "$db_url" | sed 's/sqlite+aiosqlite:\/\///' | sed 's/sqlite:\/\///')
            if [ -f "$db_path" ] || [ "$db_path" = ":memory:" ]; then
                assert_pass "SQLite database accessible"
            else
                assert_warn "SQLite file not found: ${db_path} (will be created on first use)"
            fi
        else
            assert_warn "Cannot test DB — no psql or unknown URL scheme"
        fi
    else
        assert_fail "DATABASE_URL not set"
    fi

    # Redis
    local redis_url="${REDIS_URL:-}"
    if [ -n "$redis_url" ]; then
        info "Testing Redis connectivity..."
        if check_cmd "redis-cli"; then
            if redis-cli -u "$redis_url" ping 2>/dev/null | grep -q "PONG"; then
                assert_pass "Redis connection OK"
            else
                assert_warn "Redis connection FAILED (may be intentional in dev)"
            fi
        else
            assert_warn "redis-cli not available — check Redis manually"
        fi
    else
        assert_warn "REDIS_URL not set — skipping Redis check"
    fi

    # Kafka
    local kafka_bs="${KAFKA_BOOTSTRAP_SERVERS:-}"
    if [ -n "$kafka_bs" ]; then
        info "Testing Kafka connectivity..."
        if check_cmd "kafka-topics"; then
            if kafka-topics --bootstrap-server "$kafka_bs" --list &>/dev/null; then
                assert_pass "Kafka connection OK"
            else
                assert_warn "Kafka connection FAILED"
            fi
        else
            assert_warn "kafka-topics not available — check Kafka manually"
        fi
    else
        assert_warn "KAFKA_BOOTSTRAP_SERVERS not set — skipping Kafka check"
    fi

    # RabbitMQ
    local rabbitmq_url="${RABBITMQ_URL:-}"
    if [ -n "$rabbitmq_url" ] && [ "$rabbitmq_url" != "amqp://guest:guest@localhost:5672/" ]; then
        info "Testing RabbitMQ connectivity..."
        if check_cmd "rabbitmqadmin"; then
            if rabbitmqadmin -u guest -p guest list connections &>/dev/null; then
                assert_pass "RabbitMQ connection OK"
            else
                assert_warn "RabbitMQ connection FAILED"
            fi
        else
            assert_warn "rabbitmqadmin not available — check RabbitMQ manually"
        fi
    fi

    # API Health
    local api_base="${API_BASE:-http://localhost:8000}"
    if curl -sf --max-time 5 "${api_base}/health" &>/dev/null; then
        assert_pass "API health check OK at ${api_base}"
    else
        assert_warn "API not reachable at ${api_base} (start backend first)"
    fi
}

# ── System Resource Checks ─────────────────────────────────────────────────────
check_system_resources() {
    header "System Resources"

    if [ "${SKIP_SYSTEM}" = "true" ]; then
        assert_warn "System checks skipped (SKIP_SYSTEM=true)"
        return
    fi

    # Disk space
    info "Checking disk space..."
    local disk_avail disk_used_pct
    if check_cmd "df"; then
        disk_avail=$(df -BG . 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//' || echo "unknown")
        disk_used_pct=$(df -h . 2>/dev/null | awk 'NR==2 {print $5}' | sed 's/%//' || echo "0")
        if [ -n "$disk_avail" ] && [ "$disk_avail" != "unknown" ] && [ "$disk_avail" -gt 1 ] 2>/dev/null; then
            assert_pass "Disk space: ${disk_avail}G available (${disk_used_pct}% used)"
        else
            assert_warn "Low disk space or cannot determine: ${disk_avail:-unknown}"
        fi
    else
        assert_warn "df not available"
    fi

    # Memory
    info "Checking memory..."
    if check_cmd "free"; then
        local mem_avail mem_total
        mem_avail=$(free -m 2>/dev/null | awk '/^Mem:/ {print $7}')
        mem_total=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
        if [ -n "$mem_avail" ] && [ "$mem_avail" -gt 100 ] 2>/dev/null; then
            assert_pass "Memory: ${mem_avail}M available (${mem_total}M total)"
        else
            assert_warn "Low memory: ${mem_avail:-unknown}M available"
        fi
    else
        # Windows
        local mem_info
        mem_info=$(wmic OS get FreePhysicalMemory,TotalVisibleMemorySize 2>/dev/null | awk 'NR==2 {print $1, $2}' || echo "")
        if [ -n "$mem_info" ]; then
            assert_pass "Memory check completed"
        else
            assert_warn "Cannot check memory (no free or wmic)"
        fi
    fi

    # CPU
    info "Checking CPU..."
    if check_cmd "nproc"; then
        local cpu_count
        cpu_count=$(nproc)
        if [ "$cpu_count" -ge 2 ]; then
            assert_pass "CPU: ${cpu_count} cores"
        else
            assert_warn "CPU: only ${cpu_count} core(s) — minimum 2 recommended"
        fi
    elif check_cmd "wmic"; then
        local cpu_info
        cpu_info=$(wmic cpu get NumberOfCores 2>/dev/null | awk 'NR==2 {print $1}')
        assert_pass "CPU: ${cpu_info:-?} cores"
    else
        assert_warn "Cannot check CPU count"
    fi

    # Load average
    if check_cmd "uptime"; then
        local load
        load=$(uptime 2>/dev/null | awk -F'load average:' '{print $2}' || echo "unknown")
        assert_pass "System load: ${load}"
    fi
}

# ── Log Directory Permissions ──────────────────────────────────────────────────
check_log_dirs() {
    header "Log & Data Directory Permissions"

    local dirs=(
        "${LOG_DIR:-./logs}"
        "${COMPLIANCE_ARCHIVE_DIRECTORY:-~/.forex_trading/archives}"
        "/tmp"
        "./ml/artifacts"
    )

    for dir in "${dirs[@]}"; do
        dir="${dir/#\~/$HOME}"
        if [ -d "$dir" ]; then
            if [ -r "$dir" ] && [ -w "$dir" ]; then
                assert_pass "Directory accessible: ${dir}"
            else
                assert_warn "Directory permissions issue: ${dir}"
            fi
        else
            # Try to create it
            if mkdir -p "$dir" 2>/dev/null; then
                assert_pass "Directory created: ${dir}"
            else
                assert_warn "Cannot create directory: ${dir} (OK if not required)"
            fi
        fi
    done
}

# ── Summary ────────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    header "Summary"
    echo ""
    echo "  Passed: ${PASS_COUNT}"
    if [ "$FAIL_COUNT" -gt 0 ]; then
        echo -e "  ${RED}Failed: ${FAIL_COUNT}${NC}"
    else
        echo "  Failed: ${FAIL_COUNT}"
    fi
    if [ "$WARN_COUNT" -gt 0 ]; then
        echo -e "  ${YELLOW}Warnings: ${WARN_COUNT}${NC}"
    else
        echo "  Warnings: ${WARN_COUNT}"
    fi
    echo ""

    if [ "$FAIL_COUNT" -gt 0 ]; then
        error "Configuration validation FAILED"
        return 1
    fi
    if [ "$WARN_COUNT" -gt 0 ]; then
        warn "Configuration validated with warnings"
        return 0
    fi
    success "Configuration validation PASSED"
    return 0
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    local target="${1:-all}"

    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║         PRODUCTION CONFIG VALIDATION                       ║${NC}"
    echo -e "${MAGENTA}║         Forex AI Trading Platform                          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    info "Strict mode: ${STRICT_MODE}"
    echo ""

    # Change to project root
    cd "$(dirname "$0")/.."

    case "$target" in
        --help|-h)       show_help ;;
        --env)           validate_env_vars ;;
        --certs)         validate_certificates ;;
        --connect)       check_connectivity ;;
        --system)        check_system_resources; check_log_dirs ;;
        --watch)
            while true; do
                clear
                main all
                echo ""
                info "Watching — refresh every 30s (Ctrl+C to stop)"
                sleep "${WATCH_INTERVAL:-30}"
            done
            ;;
        all|--all|"")
            validate_env_vars
            validate_certificates
            check_connectivity
            check_system_resources
            check_log_dirs
            ;;
        *)
            error "Unknown target: ${target}"
            show_help
            exit 2
            ;;
    esac

    print_summary
    exit $?
}

main "$@"
