#!/usr/bin/env bash
# =============================================================================
# Rollback Script — Forex AI Trading Platform
# =============================================================================
# Usage:
#   ./scripts/rollback.sh <environment> [revision]
#
# Examples:
#   ./scripts/rollback.sh staging
#   ./scripts/rollback.sh production 2
#   ./scripts/rollback.sh production --to-deployment=<previous-revision>
#
# This script rolls back a deployment to a previous revision using
# Kubernetes rollout undo, with health check verification.
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
warn()     { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Input Validation ──────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    error "Usage: $0 <environment> [revision]"
    echo "  environment: staging | production"
    echo "  revision:    revision number (default: previous revision)"
    exit 1
fi

ENVIRONMENT="$1"
REVISION="${2:-}"
NAMESPACE="forex-trading-${ENVIRONMENT}"

# ── Pre-rollback Validation ───────────────────────────────────────────────────
info "=== Rollback Preparation ==="

if ! kubectl cluster-info &>/dev/null; then
    error "Cannot connect to Kubernetes cluster"
    exit 1
fi

if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    error "Namespace '${NAMESPACE}' not found"
    exit 1
fi

# Show rollout history before rollback
info "Backend rollout history:"
kubectl rollout history deployment/backend -n "${NAMESPACE}"

info ""
info "Frontend rollout history:"
kubectl rollout history deployment/frontend -n "${NAMESPACE}"

# ── Confirm Rollback ──────────────────────────────────────────────────────────
echo ""
warn "You are about to roll back ${ENVIRONMENT}."
if [ -n "${REVISION}" ]; then
    warn "Target revision: ${REVISION}"
else
    warn "Target: previous revision (undo)"
fi
echo ""
read -rp "Continue? [y/N] " CONFIRM
if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
    info "Rollback cancelled"
    exit 0
fi

# ── Rollback Backend ──────────────────────────────────────────────────────────
rollback_backend() {
    info "=== Rolling Back Backend ==="

    local rollback_args=""
    if [ -n "${REVISION}" ]; then
        rollback_args="--to-revision=${REVISION}"
    fi

    kubectl rollout undo deployment/backend \
        -n "${NAMESPACE}" \
        ${rollback_args}

    info "Waiting for backend rollback to complete..."
    if ! kubectl rollout status deployment/backend \
        -n "${NAMESPACE}" \
        --timeout=300s; then
        error "Backend rollback failed"
        return 1
    fi

    # Verify health
    local retries=0
    while [ $retries -lt 20 ]; do
        if kubectl exec -n "${NAMESPACE}" deployment/backend -- \
            curl -sf http://localhost:8000/health &>/dev/null; then
            success "Backend health check passed after rollback"
            return 0
        fi
        retries=$((retries + 1))
        sleep 5
    done

    error "Backend health check failed after rollback"
    return 1
}

# ── Rollback Frontend ──────────────────────────────────────────────────────────
rollback_frontend() {
    info "=== Rolling Back Frontend ==="

    local rollback_args=""
    if [ -n "${REVISION}" ]; then
        rollback_args="--to-revision=${REVISION}"
    fi

    kubectl rollout undo deployment/frontend \
        -n "${NAMESPACE}" \
        ${rollback_args}

    info "Waiting for frontend rollback to complete..."
    if ! kubectl rollout status deployment/frontend \
        -n "${NAMESPACE}" \
        --timeout=300s; then
        error "Frontend rollback failed"
        return 1
    fi

    local retries=0
    while [ $retries -lt 20 ]; do
        if kubectl exec -n "${NAMESPACE}" deployment/frontend -- \
            wget -q -O - http://localhost:3000 &>/dev/null; then
            success "Frontend health check passed after rollback"
            return 0
        fi
        retries=$((retries + 1))
        sleep 5
    done

    error "Frontend health check failed after rollback"
    return 1
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    info "============================================"
    info "  Rolling Back ${ENVIRONMENT}"
    if [ -n "${REVISION}" ]; then
        info "  Revision: ${REVISION}"
    else
        info "  Revision: previous (undo)"
    fi
    info "============================================"

    if ! rollback_backend; then
        error "Backend rollback failed — manual intervention required"
        exit 1
    fi

    if ! rollback_frontend; then
        error "Frontend rollback failed — manual intervention required"
        exit 1
    fi

    # Show current state
    info ""
    info "Post-rollback state:"
    kubectl get pods -n "${NAMESPACE}" -o wide

    success "============================================"
    success "  Rollback of ${ENVIRONMENT} COMPLETE"
    success "============================================"
}

main "$@"
