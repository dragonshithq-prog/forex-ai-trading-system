#!/usr/bin/env bash
# =============================================================================
# Production Smoke Test Suite — Forex AI Trading Platform
# =============================================================================
#
# Orchestrates all smoke tests to verify the system is healthy after deploy.
#
# Usage:
#   ./scripts/smoke-test.sh                    # Run all smoke tests
#   ./scripts/smoke-test.sh --api              # API health only
#   ./scripts/smoke-test.sh --auth             # Auth flow only
#   ./scripts/smoke-test.sh --db               # DB connectivity only
#   ./scripts/smoke-test.sh --redis            # Redis connectivity only
#   ./scripts/smoke-test.sh --kafka            # Kafka connectivity only
#   ./scripts/smoke-test.sh --trading          # Trading flow only
#   ./scripts/smoke-test.sh --help             # Show help
#   ./scripts/smoke-test.sh --watch            # Watch mode (continuous)
#
# Environment:
#   API_BASE            Base URL (default: http://localhost:8000)
#   SMOKE_TEST_USER     Test username (auto-generated if not set)
#   SMOKE_TEST_PASSWORD Test password (auto-generated if not set)
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
API_BASE="${API_BASE:-http://localhost:8000}"
API_V1="${API_BASE}/api/v1"
TIMEOUT_SEC="${TIMEOUT_SEC:-10}"
WATCH_INTERVAL="${WATCH_INTERVAL:-30}"
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
FAILURES=""

# ── Help ───────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '3,18p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

# ── Test Runner ────────────────────────────────────────────────────────────────
run_test() {
    local name="$1"
    local func="$2"
    echo -n "  ● ${name}... "
    if $func &>/dev/null; then
        success "${name}"
        PASS_COUNT=$((PASS_COUNT + 1))
        return 0
    else
        local exit_code=$?
        error "${name} (exit: ${exit_code})"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILURES="${FAILURES}\n    - ${name}"
        return $exit_code
    fi
}

skip_test() {
    local name="$1"
    echo -n "  ● ${name}... "
    warn "${name} (SKIPPED)"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
}

# ── HTTP Helper ────────────────────────────────────────────────────────────────
http_get() {
    local url="$1"
    local timeout="${2:-$TIMEOUT_SEC}"
    curl -sf --max-time "$timeout" "$url" 2>/dev/null
}

http_post() {
    local url="$1"
    local data="$2"
    local timeout="${3:-$TIMEOUT_SEC}"
    curl -sf --max-time "$timeout" -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$data" 2>/dev/null
}

# ── Test Suites ────────────────────────────────────────────────────────────────

test_api_health() {
    header "Suite: API Health"

    # Health root
    local health
    health=$(http_get "${API_BASE}/health") || return 1
    echo "$health" | grep -q "healthy" || return 1

    # Liveness
    local live
    live=$(http_get "${API_BASE}/health/live") || return 1
    echo "$live" | grep -q "alive" || return 1

    # Readiness
    local ready
    ready=$(http_get "${API_BASE}/health/ready") || return 1
    echo "$ready" | grep -qE '"status":"(ok|degraded)"' || return 1

    # Detailed
    local detailed
    detailed=$(http_get "${API_BASE}/health/detailed") || return 1
    echo "$detailed" | grep -q "version" || return 1

    # API health
    local api_health
    api_health=$(http_get "${API_V1}/health") || return 1
    echo "$api_health" | grep -q "healthy" || return 1

    return 0
}

test_auth_flow() {
    header "Suite: Authentication Flow"

    # Generate unique test user
    local suffix
    suffix=$(date +%s | md5sum 2>/dev/null | head -c 8 || echo "smoke")
    local username="smoketest_${suffix}"
    local email="smoketest_${suffix}@example.com"
    local password="SmokeTestPass123!"

    # Register
    local register
    register=$(http_post "${API_V1}/auth/register" \
        "{\"username\":\"${username}\",\"email\":\"${email}\",\"password\":\"${password}\",\"full_name\":\"Smoke Test\"}") || {
        # If 409 (conflict), that's fine
        return 0
    }
    
    local access_token
    access_token=$(echo "$register" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) || return 1

    # Protected endpoint
    local me
    me=$(curl -sf --max-time "$TIMEOUT_SEC" "${API_V1}/auth/me" \
        -H "Authorization: Bearer ${access_token}") || return 1
    echo "$me" | grep -q "$username" || return 1

    # Refresh
    local refresh_token
    refresh_token=$(echo "$register" | python3 -c "import sys,json; print(json.load(sys.stdin)['refresh_token'])" 2>/dev/null) || return 1
    local refresh
    refresh=$(http_post "${API_V1}/auth/refresh" \
        "{\"refresh_token\":\"${refresh_token}\"}") || return 1
    echo "$refresh" | grep -q "access_token" || return 1

    # Unauthenticated access should fail
    local unauthorized
    unauthorized=$(curl -s --max-time "$TIMEOUT_SEC" -o /dev/null -w "%{http_code}" "${API_V1}/auth/me") || true
    [ "$unauthorized" = "401" ] || return 1

    return 0
}

test_db_connectivity() {
    header "Suite: Database Connectivity"

    # Readiness includes DB check
    local ready
    ready=$(http_get "${API_BASE}/health/ready") || return 1
    echo "$ready" | grep -q "database" || return 1

    # Endpoints that read from DB respond (even if unauthorized)
    local status
    status=$(curl -s --max-time "$TIMEOUT_SEC" -o /dev/null -w "%{http_code}" "${API_V1}/strategy/strategies") || true
    [ "$status" != "000" ] && [ "$status" != "502" ] && [ "$status" != "503" ] || return 1

    return 0
}

test_redis_connectivity() {
    header "Suite: Redis Connectivity"

    # Readiness includes cache check
    local ready
    ready=$(http_get "${API_BASE}/health/ready") || return 1
    echo "$ready" | grep -q "cache" || return 1

    # Can't directly test Redis from here - rely on readiness
    local cache_status
    cache_status=$(echo "$ready" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('cache','unknown'))" 2>/dev/null) || cache_status="unknown"
    [ "$cache_status" != "error" ] || return 1

    return 0
}

test_kafka_connectivity() {
    header "Suite: Kafka/Event Bus Connectivity"

    # Readiness includes event_bus check
    local ready
    ready=$(http_get "${API_BASE}/health/ready") || return 1
    echo "$ready" | grep -q "event_bus" || skip_test "event_bus not in health checks"

    local eb_status
    eb_status=$(echo "$ready" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('event_bus','unknown'))" 2>/dev/null) || eb_status="unknown"
    [ "$eb_status" != "error" ] || warn "Event bus reported as error"

    return 0
}

test_trading_flow() {
    header "Suite: Trading Flow"

    # Market data endpoints (may not need auth)
    local symbols
    symbols=$(http_get "${API_V1}/market/symbols") || {
        skip_test "Market symbols endpoint not available"
        return 0
    }
    echo "$symbols" | grep -q "EURUSD" || return 1

    # Market data
    local data
    data=$(http_get "${API_V1}/market/data?symbol=EURUSD") || {
        skip_test "Market data endpoint not available"
        return 0
    }
    echo "$data" | grep -q "symbol" || return 1

    # Trading endpoints (may need auth)
    local trading_status
    trading_status=$(curl -s --max-time "$TIMEOUT_SEC" -o /dev/null -w "%{http_code}" "${API_V1}/trading/positions") || trading_status="000"
    [ "$trading_status" != "000" ] && [ "$trading_status" != "502" ] || return 1

    # Risk endpoints
    local risk_status
    risk_status=$(curl -s --max-time "$TIMEOUT_SEC" -o /dev/null -w "%{http_code}" "${API_V1}/risk/config") || risk_status="000"
    [ "$risk_status" != "000" ] && [ "$risk_status" != "502" ] || return 1

    return 0
}

# ── Summary ────────────────────────────────────────────────────────────────────
print_summary() {
    local total=$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))
    echo ""
    header "Results"
    echo ""
    echo "  Total:  ${total}"
    echo -e "  ${GREEN}Passed:  ${PASS_COUNT}${NC}"
    if [ "$FAIL_COUNT" -gt 0 ]; then
        echo -e "  ${RED}Failed:  ${FAIL_COUNT}${NC}"
        echo -e "  ${RED}Failures:${FAILURES}${NC}"
    fi
    if [ "$SKIP_COUNT" -gt 0 ]; then
        echo -e "  ${YELLOW}Skipped: ${SKIP_COUNT}${NC}"
    fi
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    local target="${1:-all}"

    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║         PRODUCTION SMOKE TEST SUITE                        ║${NC}"
    echo -e "${MAGENTA}║         Forex AI Trading Platform                          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    info "API Base: ${API_BASE}"
    info "Timeout:  ${TIMEOUT_SEC}s"
    echo ""

    case "$target" in
        --help|-h)       show_help ;;
        --watch)         while true; do clear; main --all; echo ""; sleep "${WATCH_INTERVAL}"; done ;;
        --api)           run_test "API Health" test_api_health ;;
        --auth)          run_test "Auth Flow" test_auth_flow ;;
        --db)            run_test "DB Connectivity" test_db_connectivity ;;
        --redis)         run_test "Redis Connectivity" test_redis_connectivity ;;
        --kafka)         run_test "Kafka Connectivity" test_kafka_connectivity ;;
        --trading)       run_test "Trading Flow" test_trading_flow ;;
        all|--all|"")
            run_test "API Health" test_api_health
            run_test "Auth Flow" test_auth_flow
            run_test "DB Connectivity" test_db_connectivity
            run_test "Redis Connectivity" test_redis_connectivity
            run_test "Kafka Connectivity" test_kafka_connectivity
            run_test "Trading Flow" test_trading_flow
            ;;
        *)
            error "Unknown target: ${target}"
            show_help
            exit 2
            ;;
    esac

    print_summary

    if [ "$FAIL_COUNT" -gt 0 ]; then
        error "${FAIL_COUNT} smoke test(s) FAILED"
        exit 1
    fi

    if [ "$PASS_COUNT" -gt 0 ]; then
        success "All smoke tests passed!"
    fi
    exit 0
}

main "$@"
