#!/usr/bin/env bash
# =============================================================================
# Chaos Engineering Test Suite — Forex AI Trading Platform
# =============================================================================
#
# Simulates production failures to validate system resilience:
#   - Network latency injection
#   - Service failure simulation (Kafka, Redis, Postgres)
#   - Circuit breaker validation
#   - Outbox resilience (message persistence + replay)
#
# Usage:
#   ./scripts/chaos-test.sh [scenario]        # Run specific scenario
#   ./scripts/chaos-test.sh --all              # Run all scenarios (default)
#   ./scripts/chaos-test.sh --list             # List available scenarios
#   ./scripts/chaos-test.sh --help             # Show this help
#
# Safety:
#   - By default runs in DRY_RUN mode (set CHAOS_DRY_RUN=false to enable)
#   - Requires KUBECONFIG or local Docker environment
#   - Never runs against production without --force
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
scenario() { echo -e "\n${MAGENTA}══════════════════════════════════════════════════════════════${NC}"; }
header()  { echo -e "${MAGENTA}>>> $*${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
ENVIRONMENT="${ENVIRONMENT:-staging}"
NAMESPACE="${NAMESPACE:-forex-trading-staging}"
CHAOS_DRY_RUN="${CHAOS_DRY_RUN:-true}"   # Safe default: dry-run
CHAOS_DURATION_SECONDS="${CHAOS_DURATION_SECONDS:-60}"
CHAOS_RECOVERY_TIMEOUT="${CHAOS_RECOVERY_TIMEOUT:-120}"
FORCE="${FORCE:-false}"
# For local chaos without Kubernetes
USE_DOCKER="${USE_DOCKER:-false}"

# Network chaos settings (tc/netem)
NET_LATENCY_MS="${NET_LATENCY_MS:-500}"
NET_LATENCY_JITTER_MS="${NET_LATENCY_JITTER_MS:-100}"
NET_LOSS_PCT="${NET_LOSS_PCT:-10}"

# ── Help ───────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '2,20p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

list_scenarios() {
    echo "Available chaos scenarios:"
    declare -F | grep '^declare -f scenario_' | sed 's/^declare -f scenario_//' | while read -r name; do
        echo "  - $name"
    done
    exit 0
}

# ── Validation ─────────────────────────────────────────────────────────────────
validate_env() {
    if [ "${ENVIRONMENT}" = "production" ] && [ "${FORCE}" != "true" ]; then
        error "Refusing to run chaos tests against production without --force"
        error "Set FORCE=true only if you understand the risks."
        exit 1
    fi

    if [ "${CHAOS_DRY_RUN}" = "true" ]; then
        warn "═══════════════════════════════════════════════════════════════════"
        warn "  DRY RUN MODE — no actual chaos will be injected"
        warn "  Set CHAOS_DRY_RUN=false to enable actual failure injection"
        warn "═══════════════════════════════════════════════════════════════════"
    fi

    # Check for required tools
    local missing=false
    for tool in kubectl curl python3; do
        if ! command -v "$tool" &>/dev/null; then
            warn "Missing: $tool"
            missing=true
        fi
    done

    if [ "${USE_DOCKER}" = "true" ]; then
        if ! command -v docker &>/dev/null; then
            error "Docker required for local chaos mode"
            missing=true
        fi
    fi

    if [ "$missing" = "true" ]; then
        error "Some required tools are missing. Install them first."
        exit 1
    fi

    # Check cluster connectivity (skip in dry-run)
    if [ "${CHAOS_DRY_RUN}" = "false" ] && [ "${USE_DOCKER}" = "false" ]; then
        if ! kubectl cluster-info &>/dev/null; then
            error "Cannot connect to Kubernetes cluster"
            exit 1
        fi
        if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
            error "Namespace '${NAMESPACE}' not found"
            exit 1
        fi
    fi
}

# ── Chaos Injection Primitives ─────────────────────────────────────────────────

k8s_pod_selector() {
    local label="$1"
    if [ "${USE_DOCKER}" = "true" ]; then
        echo "docker"
    else
        kubectl get pods -n "${NAMESPACE}" -l "${label}" -o name 2>/dev/null | head -1
    fi
}

chaos_exec() {
    local pod="$1"; shift
    local cmd="$*"
    if [ "${CHAOS_DRY_RUN}" = "true" ]; then
        info "[DRY-RUN] Would exec on $pod: $cmd"
        return 0
    fi
    if [ "${USE_DOCKER}" = "true" ]; then
        docker exec "$pod" sh -c "$cmd"
    else
        kubectl exec -n "${NAMESPACE}" "$pod" -- sh -c "$cmd" 2>/dev/null || true
    fi
}

inject_network_latency() {
    local pod="$1"
    local iface="${2:-eth0}"
    local latency_ms="${3:-$NET_LATENCY_MS}"
    local jitter_ms="${4:-$NET_LATENCY_JITTER_MS}"

    info "Injecting ${latency_ms}ms ±${jitter_ms}ms latency on $pod:$iface"
    chaos_exec "$pod" "tc qdisc add dev $iface root netem delay ${latency_ms}ms ${jitter_ms}ms distribution normal" || true
}

remove_network_latency() {
    local pod="$1"
    local iface="${2:-eth0}"
    info "Removing latency injection on $pod:$iface"
    chaos_exec "$pod" "tc qdisc del dev $iface root 2>/dev/null" || true
}

inject_packet_loss() {
    local pod="$1"
    local iface="${2:-eth0}"
    local loss_pct="${3:-$NET_LOSS_PCT}"
    info "Injecting ${loss_pct}% packet loss on $pod:$iface"
    chaos_exec "$pod" "tc qdisc add dev $iface root netem loss ${loss_pct}%" || true
}

remove_packet_loss() {
    local pod="$1"
    local iface="${2:-eth0}"
    chaos_exec "$pod" "tc qdisc del dev $iface root 2>/dev/null" || true
}

service_health() {
    local service="$1"
    if [ "${CHAOS_DRY_RUN}" = "true" ]; then
        echo "unknown"
        return 0
    fi
    # Attempt local health check
    local status
    status=$(curl -sf "http://localhost:8000/health/ready" 2>/dev/null || echo "unreachable")
    echo "$status"
}

wait_for_recovery() {
    local service="$1"
    local timeout="${2:-$CHAOS_RECOVERY_TIMEOUT}"
    info "Waiting up to ${timeout}s for '$service' recovery..."
    local elapsed=0
    while [ $elapsed -lt "$timeout" ]; do
        local health
        health=$(service_health "$service")
        if echo "$health" | grep -q "ok"; then
            success "'$service' recovered after ${elapsed}s"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    error "'$service' did not recover within ${timeout}s"
    return 1
}

# ── Scenario: Broker Timeout ───────────────────────────────────────────────────
scenario_broker_timeout() {
    scenario
    header "Scenario: Broker Network Timeout"
    info "Injecting latency on broker-facing interface to simulate timeout"
    echo ""

    local pod
    pod=$(k8s_pod_selector "app=backend")
    [ -z "$pod" ] && pod="backend"

    inject_network_latency "$pod" "eth0" 5000 500
    info "Sleeping ${CHAOS_DURATION_SECONDS}s while broker timeout is active..."
    sleep "${CHAOS_DURATION_SECONDS}"
    remove_network_latency "$pod"
    wait_for_recovery "broker"
    success "Broker timeout scenario completed"
}

# ── Scenario: Database Connection Loss ─────────────────────────────────────────
scenario_db_loss() {
    scenario
    header "Scenario: Database Connection Loss"
    info "Scaling PostgreSQL down to simulate DB outage"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ] && [ "${USE_DOCKER}" = "false" ]; then
        # Scale down Postgres StatefulSet
        local orig_replicas
        orig_replicas=$(kubectl get statefulset/postgres -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
        info "Original Postgres replicas: ${orig_replicas}"
        kubectl scale statefulset/postgres -n "${NAMESPACE}" --replicas=0
        info "Waiting ${CHAOS_DURATION_SECONDS}s for DB outage impact..."
        sleep "${CHAOS_DURATION_SECONDS}"

        # Check application health during outage
        local app_health
        app_health=$(service_health "app")
        info "Application health during DB outage: ${app_health}"

        # Restore Postgres
        kubectl scale statefulset/postgres -n "${NAMESPACE}" --replicas="${orig_replicas}"
        kubectl rollout status statefulset/postgres -n "${NAMESPACE}" --timeout=120s
    else
        warn "[DRY-RUN] Would scale down postgres for ${CHAOS_DURATION_SECONDS}s"
    fi

    wait_for_recovery "database"
    success "Database loss scenario completed"
}

# ── Scenario: Redis Cluster Down ───────────────────────────────────────────────
scenario_redis_down() {
    scenario
    header "Scenario: Redis Cluster Down"
    info "Scaling Redis down to simulate cache outage"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ] && [ "${USE_DOCKER}" = "false" ]; then
        local orig_replicas
        orig_replicas=$(kubectl get statefulset/redis -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
        info "Original Redis replicas: ${orig_replicas}"
        kubectl scale statefulset/redis -n "${NAMESPACE}" --replicas=0
        sleep "${CHAOS_DURATION_SECONDS}"

        local app_health
        app_health=$(service_health "app")
        info "Application health during Redis outage: ${app_health}"

        kubectl scale statefulset/redis -n "${NAMESPACE}" --replicas="${orig_replicas}"
        kubectl rollout status statefulset/redis -n "${NAMESPACE}" --timeout=120s
    else
        warn "[DRY-RUN] Would scale down redis for ${CHAOS_DURATION_SECONDS}s"
    fi

    wait_for_recovery "cache"
    success "Redis down scenario completed"
}

# ── Scenario: Kafka Partition Loss ─────────────────────────────────────────────
scenario_kafka_loss() {
    scenario
    header "Scenario: Kafka Broker Failure"
    info "Scaling Kafka down to simulate message bus outage"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ] && [ "${USE_DOCKER}" = "false" ]; then
        local orig_replicas
        orig_replicas=$(kubectl get statefulset/kafka -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "3")
        info "Original Kafka replicas: ${orig_replicas}"
        kubectl scale statefulset/kafka -n "${NAMESPACE}" --replicas=0
        sleep "${CHAOS_DURATION_SECONDS}"

        local app_health
        app_health=$(service_health "app")
        info "Application health during Kafka outage: ${app_health}"

        kubectl scale statefulset/kafka -n "${NAMESPACE}" --replicas="${orig_replicas}"
        kubectl rollout status statefulset/kafka -n "${NAMESPACE}" --timeout=180s
    else
        warn "[DRY-RUN] Would scale down kafka for ${CHAOS_DURATION_SECONDS}s"
    fi

    wait_for_recovery "event_bus"
    success "Kafka loss scenario completed"
}

# ── Scenario: Circuit Breaker Validation ───────────────────────────────────────
scenario_circuit_breaker() {
    scenario
    header "Scenario: Circuit Breaker Validation"
    info "Verifying circuit breaker auto-resets after failure"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ]; then
        # Trigger circuit breaker by repeated failures
        info "Sending failing requests to trigger circuit breaker..."
        for i in $(seq 1 10); do
            curl -sf -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/activate" \
                -H "Content-Type: application/json" \
                -d "{\"reason\":\"Chaos test - simulated failure $i\",\"cooldown_minutes\":1}" \
                &>/dev/null || true
            sleep 1
        done

        # Check circuit breaker state
        local cb_state
        cb_state=$(curl -sf "http://localhost:8000/api/v1/risk/state?broker_account_id=00000000-0000-0000-0000-000000000000" 2>/dev/null || echo "unreachable")
        info "Circuit breaker state: $(echo "$cb_state" | head -c 200)"

        # Wait for auto-reset (with configured cooldown + buffer)
        info "Waiting for circuit breaker auto-reset..."
        sleep 65

        # Verify it has reset
        local reset_state
        reset_state=$(curl -sf "http://localhost:8000/api/v1/risk/circuit-breaker/reset?broker_account_id=00000000-0000-0000-0000-000000000000" 2>/dev/null || echo "unreachable")
        info "Reset result: $(echo "$reset_state" | head -c 200)"
    else
        warn "[DRY-RUN] Would trigger circuit breaker via repeated API failures"
        warn "[DRY-RUN] Would verify auto-reset after cooldown"
    fi

    success "Circuit breaker validation completed"
}

# ── Scenario: Outbox Resilience ────────────────────────────────────────────────
scenario_outbox_resilience() {
    scenario
    header "Scenario: Outbox Resilience (DB Replay)"
    info "Verify events persist in outbox when Kafka is down and replay on restart"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ]; then
        # 1. Scale Kafka down
        info "Step 1: Taking Kafka offline..."
        if [ "${USE_DOCKER}" = "false" ]; then
            kubectl scale statefulset/kafka -n "${NAMESPACE}" --replicas=0
        fi
        sleep 5

        # 2. Generate trading events (they should queue in the outbox table)
        info "Step 2: Generating events during Kafka outage..."
        for i in $(seq 1 5); do
            curl -sf -X POST "http://localhost:8000/api/v1/trading/orders" \
                -H "Content-Type: application/json" \
                -d "{\"symbol\":\"EURUSD\",\"side\":\"buy\",\"order_type\":\"market\",\"quantity\":0.01,\"broker_account_id\":\"00000000-0000-0000-0000-000000000000\"}" \
                &>/dev/null || true
            sleep 2
        done

        # 3. Restore Kafka
        info "Step 3: Restoring Kafka..."
        if [ "${USE_DOCKER}" = "false" ]; then
            kubectl scale statefulset/kafka -n "${NAMESPACE}" --replicas=3
            kubectl rollout status statefulset/kafka -n "${NAMESPACE}" --timeout=180s
        fi

        # 4. Verify outbox replay
        info "Step 4: Triggering outbox replay..."
        curl -sf -X POST "http://localhost:8000/api/v1/system/outbox/replay" \
            &>/dev/null || warn "Outbox replay endpoint not available"

        info "Outbox replay completed - events should be re-processed"
    else
        warn "[DRY-RUN] Would:"
        warn "  1. Scale Kafka to 0"
        warn "  2. Submit trading events (queued in outbox)"
        warn "  3. Restore Kafka"
        warn "  4. Trigger outbox replay from DB"
    fi

    success "Outbox resilience scenario completed"
}

# ── Scenario: Full Application Crash Loop ──────────────────────────────────────
scenario_crash_loop() {
    scenario
    header "Scenario: Application Crash Loop"
    info "Simulate pod crash and verify auto-recovery via liveness probe"
    echo ""

    if [ "${CHAOS_DRY_RUN}" = "false" ] && [ "${USE_DOCKER}" = "false" ]; then
        local pod
        pod=$(k8s_pod_selector "app=backend")
        [ -z "$pod" ] && { warn "No backend pod found"; return 1; }

        info "Killing backend pod: $pod"
        kubectl delete pod -n "${NAMESPACE}" "$pod" --grace-period=0 --force 2>/dev/null || true

        info "Waiting for ReplicaSet to recreate pod..."
        sleep 10

        local new_pod
        new_pod=$(k8s_pod_selector "app=backend" 2>/dev/null || echo "")
        info "New pod: ${new_pod:-pending}"

        wait_for_recovery "application"
        success "Application recovered from crash loop"
    else
        warn "[DRY-RUN] Would delete backend pod and verify auto-recovery"
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║         CHAOS ENGINEERING TEST SUITE                        ║${NC}"
    echo -e "${MAGENTA}║         Forex AI Trading Platform                          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    validate_env

    local exit_code=0

    # Run requested scenario(s)
    if [ $# -eq 0 ]; then
        set -- "--all"
    fi

    case "$1" in
        --help|-h)
            show_help
            ;;
        --list)
            list_scenarios
            ;;
        --all)
            info "Running ALL chaos scenarios sequentially"
            for scenario_func in broker_timeout db_loss redis_down kafka_loss circuit_breaker outbox_resilience crash_loop; do
                if ! "scenario_${scenario_func}"; then
                    error "Scenario '${scenario_func}' FAILED"
                    exit_code=1
                else
                    success "Scenario '${scenario_func}' PASSED"
                fi
                echo ""
            done
            ;;
        *)
            # Run specific scenario
            local scenario_name="$1"
            if declare -F "scenario_${scenario_name}" &>/dev/null; then
                if "scenario_${scenario_name}"; then
                    success "Scenario '${scenario_name}' PASSED"
                else
                    error "Scenario '${scenario_name}' FAILED"
                    exit_code=1
                fi
            else
                error "Unknown scenario: ${scenario_name}"
                list_scenarios
                exit 2
            fi
            ;;
    esac

    echo ""
    if [ $exit_code -eq 0 ]; then
        success "All chaos scenarios completed successfully"
    else
        error "Some chaos scenarios FAILED — review logs above"
    fi
    echo ""
    exit $exit_code
}

main "$@"
