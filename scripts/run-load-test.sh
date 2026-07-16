#!/usr/bin/env bash
# =============================================================================
# Load Test Runner — Forex AI Trading Platform
# =============================================================================
#
# Runs performance and load tests to validate system throughput and scaling.
#
# Usage:
#   ./scripts/run-load-test.sh [suite]         # Run specific suite
#   ./scripts/run-load-test.sh --all           # Run all load tests (default)
#   ./scripts/run-load-test.sh --list          # List available suites
#   ./scripts/run-load-test.sh --quick         # Quick smoke-level load test
#   ./scripts/run-load-test.sh --full          # Full load test suite
#   ./scripts/run-load-test.sh --report        # Generate HTML report
#   ./scripts/run-load-test.sh --help          # Show help
#
# Environment:
#   API_BASE            Base URL (default: http://localhost:8000)
#   CONCURRENT_USERS    For throughput tests (default: 50)
#   DURATION_SECONDS    For sustained load tests (default: 60)
#   REPORT_DIR          Output directory (default: reports/load-test)
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
success() { echo -e "${GREEN}[OK]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
header()  { echo -e "\n${MAGENTA}══════════════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}$*${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
API_BASE="${API_BASE:-http://localhost:8000}"
CONCURRENT_USERS="${CONCURRENT_USERS:-50}"
DURATION_SECONDS="${DURATION_SECONDS:-60}"
REPORT_DIR="${REPORT_DIR:-reports/load-test}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RESULT_DIR="${REPORT_DIR}/${TIMESTAMP}"
EXIT_CODE=0

# Python test markers
SLOW_MARKER="${SLOW_MARKER:-slow}"
LOAD_MARKER="${LOAD_MARKER:-load}"

# ── Help ───────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '3,18p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

list_suites() {
    header "Available Load Test Suites"
    echo ""
    echo "  --quick         Quick smoke-level load test (~30s)"
    echo "  --throughput    API throughput benchmarks"
    echo "  --websocket     WebSocket connection scalability"
    echo "  --concurrent    Concurrent trader simulation"
    echo "  --full          All load tests (may take > 10 minutes)"
    echo "  --all           Same as --full"
    echo ""
}

validate_env() {
    # Check dependencies
    local missing=false
    for cmd in python3 pytest; do
        if ! command -v "$cmd" &>/dev/null; then
            warn "Missing: $cmd"
            missing=true
        fi
    done

    # Check API is reachable
    if ! curl -sf --max-time 5 "${API_BASE}/health" &>/dev/null; then
        warn "API not reachable at ${API_BASE}"
        warn "Start the backend first or set API_BASE"
        warn "Continuing anyway (tests may fail)..."
    fi

    mkdir -p "${RESULT_DIR}"
}

run_pytest() {
    local suite_name="$1"
    local extra_args="${2:-}"
    local junit_xml="${RESULT_DIR}/junit-${suite_name}.xml"

    info "Running ${suite_name} load tests..."
    info "Output: ${junit_xml}"

    cd "$(dirname "$0")/../backend"

    set +e
    python3 -m pytest \
        tests/load/ \
        -m "${LOAD_MARKER}" \
        -k "${suite_name}" \
        --junitxml="${junit_xml}" \
        -v \
        --tb=short \
        --disable-warnings \
        -q \
        ${extra_args} \
        2>&1 | tee -a "${RESULT_DIR}/output.log"
    local test_exit=$?
    set -e

    if [ $test_exit -eq 0 ] || [ $test_exit -eq 5 ]; then
        # Exit code 5 means no tests collected — that's OK if suite doesn't exist
        if [ $test_exit -eq 5 ]; then
            warn "No tests found for suite '${suite_name}'"
        else
            success "${suite_name}: PASSED"
        fi
    else
        error "${suite_name}: FAILED (exit: ${test_exit})"
        EXIT_CODE=1
    fi

    return $test_exit
}

# ── Test Selection ────────────────────────────────────────────────────────────
run_quick() {
    header "Quick Load Test (~30 seconds)"
    info "Reduced concurrency and duration"
    CONCURRENT_USERS=10 \
    python3 -m pytest \
        tests/load/test_api_throughput.py \
        tests/load/test_concurrent_traders.py \
        -m "${LOAD_MARKER}" \
        --junitxml="${RESULT_DIR}/junit-quick.xml" \
        -v --tb=short -q \
        -k "test_order_placement_throughput or test_concurrent_traders_no_deadlocks" \
        2>&1 | tee -a "${RESULT_DIR}/output.log" || EXIT_CODE=1
}

run_throughput() {
    header "Throughput Tests"
    # Run throughput-specific test classes
    CONCURRENT_USERS="${CONCURRENT_USERS}" \
    python3 -m pytest \
        tests/load/test_api_throughput.py \
        -m "${LOAD_MARKER}" \
        --junitxml="${RESULT_DIR}/junit-throughput.xml" \
        -v --tb=short -q \
        2>&1 | tee -a "${RESULT_DIR}/output.log" || EXIT_CODE=1
}

run_websocket() {
    header "WebSocket Load Tests"
    python3 -m pytest \
        tests/load/test_websocket_load.py \
        -m "${LOAD_MARKER}" \
        --junitxml="${RESULT_DIR}/junit-websocket.xml" \
        -v --tb=short -q \
        2>&1 | tee -a "${RESULT_DIR}/output.log" || EXIT_CODE=1
}

run_concurrent() {
    header "Concurrent Trader Tests"
    SIMULATED_TRADERS="${CONCURRENT_USERS}" \
    python3 -m pytest \
        tests/load/test_concurrent_traders.py \
        -m "${LOAD_MARKER}" \
        --junitxml="${RESULT_DIR}/junit-concurrent.xml" \
        -v --tb=short -q \
        2>&1 | tee -a "${RESULT_DIR}/output.log" || EXIT_CODE=1
}

run_full() {
    header "Full Load Test Suite"
    info "This will take a while (${DURATION_SECONDS}s sustained tests)..."
    info "Results: ${RESULT_DIR}"

    CONCURRENT_USERS="${CONCURRENT_USERS}" \
    python3 -m pytest \
        tests/load/ \
        -m "${LOAD_MARKER}" \
        --junitxml="${RESULT_DIR}/junit-full.xml" \
        -v --tb=short \
        --durations=10 \
        -q \
        2>&1 | tee -a "${RESULT_DIR}/output.log" || EXIT_CODE=1
}

generate_report() {
    header "Generating Load Test Report"

    # Parse JUnit XML for summary
    local total=0
    local passed=0
    local failed=0

    for xml in "${RESULT_DIR}"/junit-*.xml; do
        if [ -f "$xml" ]; then
            local t f p
            t=$(grep -c 'testcase' "$xml" 2>/dev/null || echo "0")
            f=$(grep 'failure' "$xml" 2>/dev/null | grep -v 'failures' | wc -l || echo "0")
            p=$((t - f))
            total=$((total + t))
            passed=$((passed + p))
            failed=$((failed + f))
        fi
    done

    # Generate HTML report
    cat > "${RESULT_DIR}/report.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Load Test Report — ${TIMESTAMP}</title>
    <style>
        body { font-family: -apple-system, sans-serif; margin: 40px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #00d4aa; }
        .summary { display: flex; gap: 20px; margin: 20px 0; }
        .card { background: #16213e; padding: 20px; border-radius: 8px; flex: 1; text-align: center; }
        .card h2 { margin: 0; font-size: 36px; }
        .card.pass h2 { color: #00d4aa; }
        .card.fail h2 { color: #ff6b6b; }
        .card.total h2 { color: #ffd93d; }
        .detail { background: #16213e; padding: 20px; border-radius: 8px; margin: 10px 0; }
        pre { background: #0f3460; padding: 10px; border-radius: 4px; overflow-x: auto; }
        .footer { margin-top: 40px; color: #888; font-size: 12px; }
    </style>
</head>
<body>
    <h1>Load Test Report</h1>
    <p>Timestamp: ${TIMESTAMP} | API: ${API_BASE}</p>
    <div class="summary">
        <div class="card total"><h2>${total}</h2><p>Total</p></div>
        <div class="card pass"><h2>${passed}</h2><p>Passed</p></div>
        <div class="card fail"><h2>${failed}</h2><p>Failed</p></div>
    </div>
    <div class="detail">
        <h3>Test Output</h3>
        <pre>$(cat "${RESULT_DIR}/output.log" 2>/dev/null | tail -100)</pre>
    </div>
    <div class="footer">
        <p>Forex AI Trading Platform — Generated by load test runner</p>
    </div>
</body>
</html>
EOF

    info "HTML report: ${RESULT_DIR}/report.html"
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    local target="${1:---quick}"

    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║         LOAD TEST RUNNER                                   ║${NC}"
    echo -e "${MAGENTA}║         Forex AI Trading Platform                          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    info "API Base:        ${API_BASE}"
    info "Concurrent Users: ${CONCURRENT_USERS}"
    info "Duration:        ${DURATION_SECONDS}s"
    info "Report:          ${RESULT_DIR}"
    echo ""

    validate_env

    case "$target" in
        --help|-h)       show_help ;;
        --list)          list_suites ;;
        --quick)         run_quick ;;
        --throughput)    run_throughput ;;
        --websocket)     run_websocket ;;
        --concurrent)    run_concurrent ;;
        --full|--all)    run_full ;;
        --report)        generate_report ;;
        *)
            # Assume it's a pytest -k expression
            run_pytest "$target"
            ;;
    esac

    # Always generate report if we ran tests
    if [ "$target" != "--help" ] && [ "$target" != "--list" ] && [ "$target" != "--report" ]; then
        generate_report
    fi

    echo ""
    if [ $EXIT_CODE -eq 0 ]; then
        success "Load tests completed successfully"
    else
        error "Some load tests FAILED — review report for details"
        info "Report: ${RESULT_DIR}/report.html"
    fi
    exit $EXIT_CODE
}

main "$@"
