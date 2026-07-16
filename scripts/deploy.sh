#!/usr/bin/env bash
# =============================================================================
# Zero-Downtime Deployment Script — Forex AI Trading Platform
# =============================================================================
# Usage:
#   ./scripts/deploy.sh <environment> <image-tag>
#
# Examples:
#   ./scripts/deploy.sh staging sha-a1b2c3d
#   ./scripts/deploy.sh production v1.2.3
#
# This script performs a rolling update with health check polling,
# automatic rollback on failure, and pre/post deployment validation.
# =============================================================================

set -euo pipefail

# ── Color Output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Input Validation ──────────────────────────────────────────────────────────
if [ $# -lt 2 ]; then
    error "Usage: $0 <environment> <image-tag>"
    echo "  environment: staging | production"
    echo "  image-tag:   sha-a1b2c3d | v1.2.3 | latest"
    exit 1
fi

ENVIRONMENT="$1"
IMAGE_TAG="$2"
NAMESPACE="forex-trading-${ENVIRONMENT}"
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAME="${IMAGE_NAME:-org/forex-trading}"
BACKEND_IMAGE="${REGISTRY}/${IMAGE_NAME}/backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${REGISTRY}/${IMAGE_NAME}/frontend:${IMAGE_TAG}"
ROLLBACK_ON_FAILURE="${ROLLBACK_ON_FAILURE:-true}"
MAX_RETRIES=30
RETRY_INTERVAL=10

# ── Pre-deployment Validation ─────────────────────────────────────────────────
info "=== Pre-deployment Validation ==="
info "Environment: ${ENVIRONMENT}"
info "Backend image: ${BACKEND_IMAGE}"
info "Frontend image: ${FRONTEND_IMAGE}"

# Check kubectl connectivity
if ! kubectl cluster-info &>/dev/null; then
    error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
    exit 1
fi

# Check namespace exists
if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    error "Namespace '${NAMESPACE}' does not exist. Create it first."
    exit 1
fi

# Check current deployment state
info "Current deployment state:"
kubectl get deployment -n "${NAMESPACE}" -o wide 2>/dev/null || true

# Save current image tags for rollback
BACKEND_PREVIOUS_IMAGE=$(kubectl get deployment backend -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")
FRONTEND_PREVIOUS_IMAGE=$(kubectl get deployment frontend -n "${NAMESPACE}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")

success "Pre-deployment validation passed"

# ── Deploy Backend ────────────────────────────────────────────────────────────
deploy_backend() {
    info "=== Deploying Backend ==="
    info "Setting image: ${BACKEND_IMAGE}"

    kubectl set image deployment/backend \
        "backend=${BACKEND_IMAGE}" \
        -n "${NAMESPACE}" \
        --record

    kubectl annotate deployment/backend \
        "kubernetes.io/change-cause=Deploy ${IMAGE_TAG} by $(whoami) at $(date -u +%FT%TZ)" \
        --overwrite \
        -n "${NAMESPACE}"

    info "Waiting for rollout to complete..."
    if ! kubectl rollout status deployment/backend \
        -n "${NAMESPACE}" \
        --timeout=300s; then
        error "Backend rollout failed"
        return 1
    fi

    # Poll health endpoint
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        local health_status
        health_status=$(kubectl exec -n "${NAMESPACE}" \
            deployment/backend -- \
            curl -sf http://localhost:8000/health 2>/dev/null || echo "failed")

        if echo "$health_status" | grep -q "healthy"; then
            success "Backend health check passed"
            return 0
        fi

        retries=$((retries + 1))
        warn "Waiting for backend health... (${retries}/${MAX_RETRIES})"
        sleep "${RETRY_INTERVAL}"
    done

    error "Backend health check failed after ${MAX_RETRIES} retries"
    return 1
}

# ── Deploy Frontend ────────────────────────────────────────────────────────────
deploy_frontend() {
    info "=== Deploying Frontend ==="
    info "Setting image: ${FRONTEND_IMAGE}"

    kubectl set image deployment/frontend \
        "frontend=${FRONTEND_IMAGE}" \
        -n "${NAMESPACE}" \
        --record

    kubectl annotate deployment/frontend \
        "kubernetes.io/change-cause=Deploy ${IMAGE_TAG} by $(whoami) at $(date -u +%FT%TZ)" \
        --overwrite \
        -n "${NAMESPACE}"

    info "Waiting for rollout to complete..."
    if ! kubectl rollout status deployment/frontend \
        -n "${NAMESPACE}" \
        --timeout=300s; then
        error "Frontend rollout failed"
        return 1
    fi

    # Poll frontend health
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        local health_status
        health_status=$(kubectl exec -n "${NAMESPACE}" \
            deployment/frontend -- \
            wget -q -O - http://localhost:3000 2>/dev/null || echo "failed")

        if [ "$health_status" != "failed" ]; then
            success "Frontend health check passed"
            return 0
        fi

        retries=$((retries + 1))
        warn "Waiting for frontend health... (${retries}/${MAX_RETRIES})"
        sleep "${RETRY_INTERVAL}"
    done

    error "Frontend health check failed after ${MAX_RETRIES} retries"
    return 1
}

# ── Post-deployment Smoke Tests ───────────────────────────────────────────────
run_smoke_tests() {
    info "=== Running Smoke Tests ==="

    local api_url
    if [ "${ENVIRONMENT}" = "production" ]; then
        api_url="https://api.yourdomain.com"
    else
        api_url="https://staging-api.yourdomain.com"
    fi

    # Test health endpoint
    local health_response
    health_response=$(curl -sf "${api_url}/health" 2>/dev/null || echo "failed")
    if echo "$health_response" | grep -q "healthy"; then
        success "Health endpoint: OK"
    else
        error "Health endpoint: FAILED"
        return 1
    fi

    # Test API response time
    local response_time
    response_time=$(curl -o /dev/null -s -w "%{time_total}" "${api_url}/health" 2>/dev/null || echo "999")
    info "Response time: ${response_time}s"
    if (( $(echo "$response_time < 2.0" | bc -l) )); then
        success "Response time: OK"
    else
        warn "Response time高于阈值"
    fi

    # Verify pod count
    local ready_replicas
    ready_replicas=$(kubectl get deployment backend \
        -n "${NAMESPACE}" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "${ready_replicas}" -ge 2 ]; then
        success "Backend replicas ready: ${ready_replicas}"
    else
        warn "Backend replicas: ${ready_replicas} (expected >= 2)"
    fi

    success "Smoke tests completed"
    return 0
}

# ── Rollback Function ──────────────────────────────────────────────────────────
rollback() {
    error "=== ROLLING BACK ==="

    if [ "${ROLLBACK_ON_FAILURE}" != "true" ]; then
        warn "ROLLBACK_ON_FAILURE is disabled. Manual intervention required."
        return 1
    fi

    if [ -n "${BACKEND_PREVIOUS_IMAGE}" ]; then
        info "Rolling back backend to: ${BACKEND_PREVIOUS_IMAGE}"
        kubectl set image deployment/backend \
            "backend=${BACKEND_PREVIOUS_IMAGE}" \
            -n "${NAMESPACE}"
        kubectl rollout status deployment/backend \
            -n "${NAMESPACE}" \
            --timeout=120s || true
    fi

    if [ -n "${FRONTEND_PREVIOUS_IMAGE}" ]; then
        info "Rolling back frontend to: ${FRONTEND_PREVIOUS_IMAGE}"
        kubectl set image deployment/frontend \
            "frontend=${FRONTEND_PREVIOUS_IMAGE}" \
            -n "${NAMESPACE}"
        kubectl rollout status deployment/frontend \
            -n "${NAMESPACE}" \
            --timeout=120s || true
    fi

    success "Rollback completed"
}

# ── Main Execution ─────────────────────────────────────────────────────────────
main() {
    info "============================================"
    info "  Deploying ${IMAGE_TAG} → ${ENVIRONMENT}"
    info "============================================"

    # Step 1: Deploy backend
    if ! deploy_backend; then
        error "Backend deployment failed"
        rollback
        exit 1
    fi

    # Step 2: Deploy frontend
    if ! deploy_frontend; then
        error "Frontend deployment failed"
        rollback
        exit 1
    fi

    # Step 3: Post-deployment validation
    if ! run_smoke_tests; then
        error "Smoke tests failed"
        rollback
        exit 1
    fi

    success "============================================"
    success "  Deployment ${IMAGE_TAG} → ${ENVIRONMENT} SUCCESSFUL"
    success "============================================"
}

main "$@"
