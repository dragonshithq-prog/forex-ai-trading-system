#!/usr/bin/env bash
# =============================================================================
# Security Audit Script — Forex AI Trading Platform
# =============================================================================
#
# Runs multiple security scanning tools to identify vulnerabilities:
#   - Dependency vulnerability scan (pip-audit, safety)
#   - SAST scan (bandit)
#   - Secret scanning (detect-secrets, truffleHog)
#   - Docker image scan (trivy)
#   - Dependency license check (pip-licenses)
#   - CVE database check
#
# Usage:
#   ./scripts/security-audit.sh [--full]     # Run all scans
#   ./scripts/security-audit.sh --deps       # Dependency scan only
#   ./scripts/security-audit.sh --sast       # Static analysis only
#   ./scripts/security-audit.sh --secrets    # Secret scanning only
#   ./scripts/security-audit.sh --docker     # Docker image scan only
#   ./scripts/security-audit.sh --license    # License check only
#   ./scripts/security-audit.sh --help       # Show help
#   ./scripts/security-audit.sh --report     # Generate HTML report
#
# Environment:
#   REPORT_DIR          Output directory (default: reports/security-audit)
#   DOCKER_IMAGE        Docker image to scan (default: ghcr.io/org/forex-trading:latest)
#   SEVERITY_THRESHOLD  Minimum severity to report (default: LOW)
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
error()   { echo -e "${RED}[FAIL]${NC}   $*"; }
header()  { echo -e "\n${MAGENTA}══════════════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}$*${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
REPORT_DIR="${REPORT_DIR:-reports/security-audit}"
DOCKER_IMAGE="${DOCKER_IMAGE:-ghcr.io/org/forex-trading:latest}"
SEVERITY_THRESHOLD="${SEVERITY_THRESHOLD:-LOW}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
RESULT_DIR="${REPORT_DIR}/${TIMESTAMP}"
EXIT_CODE=0
PYTHON_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"

# ── Help ───────────────────────────────────────────────────────────────────────
show_help() {
    sed -n '3,20p' "$0" | sed 's/^# //' | sed 's/^#$//'
    exit 0
}

# ── Setup ──────────────────────────────────────────────────────────────────────
setup() {
    mkdir -p "${RESULT_DIR}"
    info "Results directory: ${RESULT_DIR}"

    # Check Python environment
    if [ -d "${PYTHON_DIR}/.venv" ]; then
        PYTHON="${PYTHON_DIR}/.venv/bin/python"
        PIP="${PYTHON_DIR}/.venv/bin/pip"
    elif [ -d "${PYTHON_DIR}/.venv312" ]; then
        PYTHON="${PYTHON_DIR}/.venv312/bin/python"
        PIP="${PYTHON_DIR}/.venv312/bin/pip"
    else
        PYTHON="python3"
        PIP="pip3"
    fi

    info "Using Python: ${PYTHON}"
}

check_tool() {
    local tool="$1"
    local install_hint="$2"
    if ! command -v "$tool" &>/dev/null; then
        warn "${tool} not found. ${install_hint}"
        return 1
    fi
    return 0
}

install_if_missing() {
    local tool="$1"
    if ! check_tool "$tool" "Install with: pip install ${tool}"; then
        info "Installing ${tool}..."
        ${PIP} install "${tool}" 2>/dev/null || warn "Failed to install ${tool}"
    fi
}

# ── Dependency Vulnerability Scan ──────────────────────────────────────────────
scan_dependencies() {
    header "Dependency Vulnerability Scan"

    local results="${RESULT_DIR}/dependencies.txt"
    local json_results="${RESULT_DIR}/dependencies.json"

    # pip-audit
    if check_tool "pip-audit" "Install: pip install pip-audit"; then
        info "Running pip-audit..."
        cd "${PYTHON_DIR}"
        pip-audit \
            --requirement pyproject.toml \
            --format json \
            --output "${json_results}" \
            2>&1 | tee -a "${results}" || true

        local vuln_count
        vuln_count=$(python3 -c "import json; d=json.load(open('${json_results}')); print(len(d.get('vulnerabilities',[])))" 2>/dev/null || echo "0")
        info "pip-audit: ${vuln_count} vulnerabilities found"
    else
        install_if_missing "pip-audit"
    fi

    # Safety
    if check_tool "safety" "Install: pip install safety"; then
        info "Running safety check..."
        cd "${PYTHON_DIR}"
        safety check \
            --full-report \
            --file pyproject.toml \
            --output text \
            2>&1 | tee -a "${results}" || true
        safety check \
            --file pyproject.toml \
            --output json \
            > "${RESULT_DIR}/safety.json" 2>/dev/null || true
    else
        install_if_missing "safety"
    fi

    # Aggregate results
    local dep_issues
    dep_issues=$(grep -c "CVE-" "${results}" 2>/dev/null || echo "0")
    echo "${dep_issues}" > "${RESULT_DIR}/dep-count.txt"

    if [ "$dep_issues" -gt 0 ]; then
        warn "${dep_issues} dependency vulnerabilities found"
        EXIT_CODE=1
    else
        success "No dependency vulnerabilities found"
    fi
}

# ── SAST Scan (Bandit) ─────────────────────────────────────────────────────────
scan_sast() {
    header "SAST Scan (Bandit)"

    local results="${RESULT_DIR}/sast.txt"

    if check_tool "bandit" "Install: pip install bandit"; then
        info "Running bandit..."
        cd "${PYTHON_DIR}"
        bandit \
            -r src/ \
            --format json \
            --output "${RESULT_DIR}/bandit.json" \
            --severity-level all \
            --confidence-level all \
            2>&1 | tee -a "${results}" || true

        bandit \
            -r src/ \
            --format txt \
            2>&1 | tee -a "${results}" || true

        # Count issues
        local high medium low
        high=$(python3 -c "import json; d=json.load(open('${RESULT_DIR}/bandit.json')); print(sum(1 for r in d.get('results',[]) if r['issue_severity']=='HIGH'))" 2>/dev/null || echo "0")
        medium=$(python3 -c "import json; d=json.load(open('${RESULT_DIR}/bandit.json')); print(sum(1 for r in d.get('results',[]) if r['issue_severity']=='MEDIUM'))" 2>/dev/null || echo "0")
        low=$(python3 -c "import json; d=json.load(open('${RESULT_DIR}/bandit.json')); print(sum(1 for r in d.get('results',[]) if r['issue_severity']=='LOW'))" 2>/dev/null || echo "0")

        info "Bandit: H:${high} M:${medium} L:${low}"

        if [ "$high" -gt 0 ] || [ "$medium" -gt 0 ]; then
            warn "High/Medium severity issues found"
            EXIT_CODE=1
        else
            success "No high-severity SAST issues found"
        fi
    else
        install_if_missing "bandit"
        scan_sast  # Retry
    fi
}

# ── Secret Scanning ────────────────────────────────────────────────────────────
scan_secrets() {
    header "Secret Scanning"

    local results="${RESULT_DIR}/secrets.txt"

    # detect-secrets
    if check_tool "detect-secrets" "Install: pip install detect-secrets"; then
        info "Running detect-secrets..."
        cd "$(dirname "$0")/.."
        detect-secrets scan \
            --all-files \
            --exclude-files '\.venv*|\.git|node_modules|__pycache__|*.pyc' \
            --exclude-secrets 'change-me|changeme|placeholder|your-' \
            > "${RESULT_DIR}/detect-secrets.json" 2>/dev/null || true

        local secrets_found
        secrets_found=$(python3 -c "import json; d=json.load(open('${RESULT_DIR}/detect-secrets.json')); print(len(d.get('results',{}).get('secrets',[])))" 2>/dev/null || echo "0")
        echo "${secrets_found}" > "${RESULT_DIR}/secrets-count.txt"

        if [ "$secrets_found" -gt 0 ]; then
            warn "${secrets_found} potential secrets found"
            python3 -c "import json; d=json.load(open('${RESULT_DIR}/detect-secrets.json')); [print(f'  - {r.get(\"filename\",\"\")}: {r.get(\"type\",\"\")}') for r in d.get('results',{}).get('secrets',[])]" 2>/dev/null || true
            EXIT_CODE=1
        else
            success "No secrets detected"
        fi
    else
        warn "detect-secrets not available (install: pip install detect-secrets)"
    fi

    # truffleHog (if available)
    if check_tool "trufflehog" "Install: pip install trufflehog"; then
        info "Running trufflehog..."
        cd "$(dirname "$0")/.."
        trufflehog filesystem \
            --directory . \
            --exclude-paths .gitignore \
            --json \
            > "${RESULT_DIR}/trufflehog.json" 2>/dev/null || true

        local truffle_count
        truffle_count=$(python3 -c "import json; lines=open('${RESULT_DIR}/trufflehog.json').read().strip().split('\n'); print(sum(1 for l in lines if l.strip()))" 2>/dev/null || echo "0")
        info "trufflehog: ${truffle_count} findings"
    else
        warn "trufflehog not available (install: pip install trufflehog)"
    fi

    # Scan git history
    if [ -d "$(dirname "$0")/../.git" ]; then
        info "Scanning git history for secrets..."
        cd "$(dirname "$0")/.."
        git log --all --diff-filter=A --name-only --pretty=format: | sort -u | head -20 > "${RESULT_DIR}/git-history-files.txt" 2>/dev/null || true
    fi

    # Check for common secret patterns
    info "Checking for hardcoded secrets in Python files..."
    cd "${PYTHON_DIR}"
    grep -rn --include="*.py" \
        -e 'password\s*=\s*["'"'"'][^"'"'"']*["'"'"']' \
        -e 'api_key\s*=\s*["'"'"'][^"'"'"']*["'"'"']' \
        -e 'secret\s*=\s*["'"'"'][^"'"'"']*["'"'"']' \
        -e 'token\s*=\s*["'"'"'][^"'"'"']*["'"'"']' \
        src/ 2>/dev/null | grep -v '\.env\|change-me\|placeholder\|test_' \
        > "${RESULT_DIR}/hardcoded-secrets.txt" || true

    local hardcoded
    hardcoded=$(wc -l < "${RESULT_DIR}/hardcoded-secrets.txt" 2>/dev/null || echo "0")
    if [ "$hardcoded" -gt 0 ]; then
        warn "${hardcoded} potential hardcoded secrets in source"
        cat "${RESULT_DIR}/hardcoded-secrets.txt"
        EXIT_CODE=1
    fi
}

# ── Docker Image Scan ──────────────────────────────────────────────────────────
scan_docker() {
    header "Docker Image Scan"

    local results="${RESULT_DIR}/docker.txt"

    if check_tool "trivy" "Install: brew install trivy or https://trivy.dev"; then
        if docker image inspect "${DOCKER_IMAGE}" &>/dev/null 2>&1; then
            info "Scanning Docker image: ${DOCKER_IMAGE}"
            trivy image \
                --severity HIGH,CRITICAL \
                --format json \
                --output "${RESULT_DIR}/trivy.json" \
                "${DOCKER_IMAGE}" \
                2>&1 | tee -a "${results}" || true

            trivy image \
                --severity HIGH,CRITICAL \
                --format table \
                "${DOCKER_IMAGE}" \
                2>&1 | tee -a "${results}" || true

            local vulns
            vulns=$(python3 -c "import json; d=json.load(open('${RESULT_DIR}/trivy.json')); print(len(d.get('Results',[{}])[0].get('Vulnerabilities',[])))" 2>/dev/null || echo "0")
            info "Trivy: ${vulns} HIGH/CRITICAL vulnerabilities"
        else
            warn "Docker image not found locally: ${DOCKER_IMAGE}"
            info "Pull with: docker pull ${DOCKER_IMAGE}"
        fi
    else
        warn "trivy not available — skipping Docker scan"
        warn "Install: https://trivy.dev/docs/getting-started/installation/"
    fi

    # Also check Dockerfile for best practices
    if [ -f "${PYTHON_DIR}/Dockerfile" ]; then
        info "Checking Dockerfile best practices..."
        check_dockerfile "${PYTHON_DIR}/Dockerfile" | tee -a "${results}"
    fi
}

check_dockerfile() {
    local dockerfile="$1"
    local issues=0

    if ! grep -q "USER " "$dockerfile" 2>/dev/null; then
        warn "  - Dockerfile should specify a non-root USER"
        issues=$((issues + 1))
    fi
    if ! grep -q "HEALTHCHECK" "$dockerfile" 2>/dev/null; then
        warn "  - Dockerfile should include HEALTHCHECK"
        issues=$((issues + 1))
    fi
    if grep -q "apt-get install.*--no-install-recommends" "$dockerfile" 2>/dev/null; then
        :  # Good
    else
        warn "  - Consider adding --no-install-recommends to apt-get"
        issues=$((issues + 1))
    fi

    if [ "$issues" -eq 0 ]; then
        success "Dockerfile best practices: OK"
    fi
}

# ── License Check ──────────────────────────────────────────────────────────────
check_licenses() {
    header "Dependency License Check"

    local results="${RESULT_DIR}/licenses.txt"

    if check_tool "pip-licenses" "Install: pip install pip-licenses"; then
        info "Running pip-licenses..."
        cd "${PYTHON_DIR}"
        pip-licenses \
            --format json \
            --output-file "${RESULT_DIR}/pip-licenses.json" \
            2>/dev/null || true

        pip-licenses \
            --format csv \
            --output-file "${RESULT_DIR}/pip-licenses.csv" \
            2>/dev/null || true

        # Check for restricted licenses
        local restricted
        restricted=$(python3 << 'EOF' 2>/dev/null
import json
restricted_licenses = {'GPL', 'AGPL', 'LGPL', 'CPAL', 'EUPL'}
try:
    with open(f'{RESTRICTED_DIR}/pip-licenses.json') as f:
        packages = json.load(f)
    restricted_pkgs = [p for p in packages if any(r in p.get('License', '') for r in restricted_licenses)]
    for p in restricted_pkgs:
        print(f"  - {p['Name']}: {p['License']}")
    print(f"Total restricted: {len(restricted_pkgs)}")
except:
    print("0")
EOF
)
        info "${restricted}"
    else
        install_if_missing "pip-licenses"
        check_licenses
    fi
}

# ── CVE Database Check ─────────────────────────────────────────────────────────
check_cve() {
    header "CVE Database Check"

    local results="${RESULT_DIR}/cve.txt"

    # Check if we have Python vulnerability database
    if [ -f "${RESULT_DIR}/dependencies.json" ]; then
        info "Checking CVE database for known vulnerabilities..."
        python3 << 'EOF' 2>/dev/null | tee -a "${results}"
import json
try:
    with open('${RESULT_DIR}/dependencies.json') as f:
        data = json.load(f)
    vulns = data.get('vulnerabilities', [])
    for v in vulns[:20]:
        print(f"  - {v.get('id', 'N/A')}: {v.get('description', 'N/A')[:100]}")
    print(f"\nTotal CVEs: {len(vulns)}")
except Exception as e:
    print(f"Could not parse: {e}")
EOF
    fi
}

# ── HTML Report ────────────────────────────────────────────────────────────────
generate_report() {
    header "Generating Security Audit Report"

    local dep_count=$(cat "${RESULT_DIR}/dep-count.txt" 2>/dev/null || echo "0")
    local secret_count=$(cat "${RESULT_DIR}/secrets-count.txt" 2>/dev/null || echo "0")

    cat > "${RESULT_DIR}/report.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Security Audit Report — ${TIMESTAMP}</title>
    <style>
        body { font-family: -apple-system, sans-serif; margin: 40px; background: #1a1a2e; color: #e0e0e0; }
        h1 { color: #00d4aa; }
        .summary { display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }
        .card { background: #16213e; padding: 20px; border-radius: 8px; flex: 1; min-width: 150px; text-align: center; }
        .card h2 { margin: 0; font-size: 36px; }
        .card.pass h2 { color: #00d4aa; }
        .card.fail h2 { color: #ff6b6b; }
        .card.warn h2 { color: #ffd93d; }
        .section { background: #16213e; padding: 20px; border-radius: 8px; margin: 10px 0; }
        pre { background: #0f3460; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
        .footer { margin-top: 40px; color: #888; font-size: 12px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
        .badge-critical { background: #ff6b6b; color: #fff; }
        .badge-high { background: #ffa500; color: #000; }
        .badge-medium { background: #ffd93d; color: #000; }
        .badge-low { background: #6bcbff; color: #000; }
    </style>
</head>
<body>
    <h1>Security Audit Report</h1>
    <p>Timestamp: ${TIMESTAMP} | Severity Threshold: ${SEVERITY_THRESHOLD}</p>

    <div class="summary">
        <div class="card warn"><h2>${dep_count}</h2><p>Dependency Vulns</p></div>
        <div class="card warn"><h2>${secret_count}</h2><p>Potential Secrets</p></div>
    </div>

    <div class="section">
        <h3>Dependencies</h3>
        <pre>$(cat "${RESULT_DIR}/dependencies.txt" 2>/dev/null | tail -30)</pre>
    </div>

    <div class="section">
        <h3>SAST Results</h3>
        <pre>$(cat "${RESULT_DIR}/sast.txt" 2>/dev/null | tail -30)</pre>
    </div>

    <div class="section">
        <h3>Secrets</h3>
        <pre>$(cat "${RESULT_DIR}/secrets.txt" 2>/dev/null | tail -20)</pre>
    </div>

    <div class="section">
        <h3>Docker</h3>
        <pre>$(cat "${RESULT_DIR}/docker.txt" 2>/dev/null | tail -20)</pre>
    </div>

    <div class="section">
        <h3>Licenses</h3>
        <pre>$(cat "${RESULT_DIR}/licenses.txt" 2>/dev/null | tail -20)</pre>
    </div>

    <div class="footer">
        <p>Forex AI Trading Platform — Security Audit | Exit Code: ${EXIT_CODE}</p>
    </div>
</body>
</html>
EOF

    info "Report: ${RESULT_DIR}/report.html"
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    local target="${1:---full}"

    echo ""
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║         SECURITY AUDIT                                      ║${NC}"
    echo -e "${MAGENTA}║         Forex AI Trading Platform                          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    setup

    case "$target" in
        --help|-h)       show_help ;;
        --deps)          scan_dependencies ;;
        --sast)          scan_sast ;;
        --secrets)       scan_secrets ;;
        --docker)        scan_docker ;;
        --license)       check_licenses ;;
        --full|--all|"")
            scan_dependencies
            scan_sast
            scan_secrets
            scan_docker
            check_licenses
            check_cve
            generate_report
            ;;
        --report)
            generate_report
            ;;
        *)
            error "Unknown target: ${target}"
            show_help
            exit 2
            ;;
    esac

    echo ""
    if [ $EXIT_CODE -eq 0 ]; then
        success "Security audit completed — no critical issues found"
    else
        error "Security audit found issues — review report"
        info "Report: ${RESULT_DIR}/report.html"
    fi
    exit $EXIT_CODE
}

main "$@"
