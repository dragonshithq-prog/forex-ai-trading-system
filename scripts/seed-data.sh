#!/usr/bin/env bash
# =============================================================================
# Database Seed Script — Forex AI Trading Platform
# =============================================================================
# Usage:
#   ./scripts/seed-data.sh                      # Seed with defaults
#   ./scripts/seed-data.sh --environment=prod   # Seed for specific environment
#   ./scripts/seed-data.sh --dry-run            # Print actions without executing
#
# This script seeds the database with initial data:
#   - Admin user account
#   - Default risk management configurations
#   - Default trading strategies
#   - Market data configuration
#   - System settings
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
# Database connection
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-forex}"
PGDATABASE="${PGDATABASE:-forex_trading}"
PGPASSWORD="${PGPASSWORD:-}"

# Admin user defaults
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@forex-trading.local}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

# Environment
ENVIRONMENT="development"
DRY_RUN=false

# Parse arguments
for arg in "$@"; do
    case "${arg}" in
        --environment=*)
            ENVIRONMENT="${arg#*=}"
            ;;
        --dry-run)
            DRY_RUN=true
            info "DRY RUN — no changes will be made"
            ;;
        *)
            warn "Unknown argument: ${arg}"
            ;;
    esac
done

# ── Pre-flight Checks ─────────────────────────────────────────────────────────
preflight() {
    info "=== Pre-flight Checks ==="

    command -v psql >/dev/null 2>&1 || { error "psql is required but not installed"; exit 1; }

    if [ "${DRY_RUN}" = false ]; then
        info "Testing database connection..."
        PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
            -c "SELECT 1" >/dev/null 2>&1 || {
            error "Cannot connect to database"
            exit 1
        }
        success "Database connection OK"
    fi

    # Check if admin password is set
    if [ -z "${ADMIN_PASSWORD}" ] && [ "${ENVIRONMENT}" = "production" ]; then
        error "ADMIN_PASSWORD is required for production seeding"
        echo "  Set ADMIN_PASSWORD environment variable"
        exit 1
    fi
}

# ── Execute SQL Helper ─────────────────────────────────────────────────────────
execute_sql() {
    local sql="$1"
    local description="${2:-}"

    if [ -n "${description}" ]; then
        info "${description}"
    fi

    if [ "${DRY_RUN}" = true ]; then
        echo "${sql}"
        return 0
    fi

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -c "${sql}" 2>&1
}

# ── Seed Admin User ────────────────────────────────────────────────────────────
seed_admin_user() {
    info "=== Seeding Admin User ==="

    # Generate bcrypt hash if password is set
    local password_hash
    if [ -n "${ADMIN_PASSWORD}" ]; then
        if command -v python3 &>/dev/null; then
            password_hash=$(python3 -c "
import hashlib, os, base64
salt = os.urandom(16)
# Simple SHA-256 hash for seeding (use proper bcrypt in production)
h = hashlib.pbkdf2_hmac('sha256', b'${ADMIN_PASSWORD}', salt, 100000)
print(base64.b64encode(salt + h).decode())
")
        else
            warn "python3 not available; using placeholder hash"
            password_hash="PLACEHOLDER_HASH_REPLACE_IN_PRODUCTION"
        fi
    else
        # Generate a random password for development
        local random_password
        random_password=$(openssl rand -base64 16 2>/dev/null || echo "dev-password-change-me")
        ADMIN_PASSWORD="${random_password}"
        warn "Generated admin password: ${ADMIN_PASSWORD}"
        if command -v python3 &>/dev/null; then
            password_hash=$(python3 -c "
import hashlib, os, base64
salt = os.urandom(16)
h = hashlib.pbkdf2_hmac('sha256', b'${random_password}', salt, 100000)
print(base64.b64encode(salt + h).decode())
")
        else
            password_hash="PLACEHOLDER_HASH_REPLACE_IN_PRODUCTION"
        fi
    fi

    execute_sql "
    INSERT INTO users (email, username, password_hash, role, is_active, is_verified, created_at, updated_at)
    VALUES (
        '${ADMIN_EMAIL}',
        '${ADMIN_USERNAME}',
        '${password_hash}',
        'admin',
        true,
        true,
        NOW(),
        NOW()
    )
    ON CONFLICT (email) DO UPDATE SET
        username = EXCLUDED.username,
        role = 'admin',
        is_active = true,
        updated_at = NOW();
    " "Creating/updating admin user: ${ADMIN_EMAIL}"
}

# ── Seed Risk Configurations ───────────────────────────────────────────────────
seed_risk_configs() {
    info "=== Seeding Risk Configurations ==="

    execute_sql "
    INSERT INTO risk_configurations (name, description, max_position_size_pct, max_total_exposure_pct,
        max_drawdown_daily_pct, max_drawdown_total_pct, max_positions, risk_per_trade_pct,
        max_consecutive_losses, cooldown_minutes, max_daily_trades, is_active, created_at, updated_at)
    VALUES
        ('conservative', 'Conservative risk profile for new accounts', 1.0, 10.0, 2.0, 10.0, 5, 0.5, 3, 120, 20, true, NOW(), NOW()),
        ('moderate', 'Moderate risk profile for standard trading', 2.0, 20.0, 3.0, 15.0, 10, 1.0, 5, 60, 50, true, NOW(), NOW()),
        ('aggressive', 'Aggressive risk profile for experienced traders', 5.0, 30.0, 5.0, 25.0, 20, 2.0, 8, 30, 100, false, NOW(), NOW())
    ON CONFLICT (name) DO NOTHING;
    " "Creating default risk configurations"
}

# ── Seed Trading Strategies ────────────────────────────────────────────────────
seed_strategies() {
    info "=== Seeding Trading Strategies ==="

    execute_sql "
    INSERT INTO strategies (name, type, description, parameters, is_active, created_at, updated_at)
    VALUES
        ('trend_following_ema', 'TREND_FOLLOWING',
         'EMA cross-over trend following strategy with ATR-based stop loss',
         '{\"fast_period\": 12, \"slow_period\": 26, \"signal_period\": 9, \"atr_multiplier\": 2.0, \"use_trailing_stop\": true}',
         true, NOW(), NOW()),
        ('mean_reversion_rsi', 'MEAN_REVERSION',
         'RSI-based mean reversion strategy with Bollinger Band confirmation',
         '{\"rsi_period\": 14, \"rsi_overbought\": 70, \"rsi_oversold\": 30, \"bb_period\": 20, \"bb_std\": 2.0}',
         true, NOW(), NOW()),
        ('breakout_momentum', 'MOMENTUM',
         'Breakout momentum strategy using price channel and volume confirmation',
         '{\"channel_period\": 20, \"volume_multiplier\": 1.5, \"min_breakout_pips\": 10, \"trailing_stop_pips\": 20}',
         true, NOW(), NOW()),
        ('grid_trading', 'GRID',
         'Grid trading strategy for ranging markets with automatic layer management',
         '{\"grid_levels\": 10, \"grid_spacing_pips\": 10, \"take_profit_pips\": 50, \"max_open_positions\": 5}',
         false, NOW(), NOW())
    ON CONFLICT (name) DO NOTHING;
    " "Creating default trading strategies"
}

# ── Seed Market Data Configuration ─────────────────────────────────────────────
seed_market_config() {
    info "=== Seeding Market Data Configuration ==="

    execute_sql "
    INSERT INTO market_configurations (symbol, broker, timeframe, is_active, pip_value, lot_size,
        min_trade_size, max_trade_size, spread_multiplier, created_at, updated_at)
    VALUES
        ('EURUSD', 'OANDA', 'H1', true, 0.0001, 100000, 0.01, 10.0, 1.0, NOW(), NOW()),
        ('GBPUSD', 'OANDA', 'H1', true, 0.0001, 100000, 0.01, 10.0, 1.2, NOW(), NOW()),
        ('USDJPY', 'OANDA', 'H1', true, 0.01, 100000, 0.01, 10.0, 1.0, NOW(), NOW()),
        ('AUDUSD', 'OANDA', 'H1', true, 0.0001, 100000, 0.01, 10.0, 1.1, NOW(), NOW()),
        ('USDCAD', 'OANDA', 'H1', true, 0.0001, 100000, 0.01, 10.0, 1.3, NOW(), NOW())
    ON CONFLICT (symbol, broker) DO NOTHING;
    " "Creating default market data configurations"
}

# ── Seed System Settings ───────────────────────────────────────────────────────
seed_system_settings() {
    info "=== Seeding System Settings ==="

    execute_sql "
    INSERT INTO system_settings (key, value, description, category, created_at, updated_at)
    VALUES
        ('trading_enabled', 'false', 'Master switch for all trading operations', 'trading', NOW(), NOW()),
        ('paper_trading_enabled', 'true', 'Enable paper trading mode', 'trading', NOW(), NOW()),
        ('auto_trading_enabled', 'false', 'Enable fully automated trading', 'trading', NOW(), NOW()),
        ('max_daily_risk_pct', '2.0', 'Maximum daily risk as percentage of account', 'risk', NOW(), NOW()),
        ('min_ai_confidence', '0.70', 'Minimum AI consensus confidence to execute trades', 'ai', NOW(), NOW()),
        ('log_level', 'INFO', 'System-wide log level', 'monitoring', NOW(), NOW()),
        ('monitoring_enabled', 'true', 'Enable Prometheus metrics export', 'monitoring', NOW(), NOW()),
        ('audit_log_enabled', 'true', 'Enable audit trail logging', 'security', NOW(), NOW()),
        ('rate_limit_enabled', 'true', 'Enable API rate limiting', 'security', NOW(), NOW()),
        ('maintenance_mode', 'false', 'Put system in maintenance mode', 'system', NOW(), NOW())
    ON CONFLICT (key) DO NOTHING;
    " "Creating default system settings"
}

# ── Verify Seed Data ────────────────────────────────────────────────────────────
verify_seed() {
    if [ "${DRY_RUN}" = true ]; then
        return 0
    fi

    info "=== Verifying Seed Data ==="

    execute_sql "
    SELECT 'users' as table_name, COUNT(*) as record_count FROM users
    UNION ALL
    SELECT 'risk_configurations', COUNT(*) FROM risk_configurations
    UNION ALL
    SELECT 'strategies', COUNT(*) FROM strategies
    UNION ALL
    SELECT 'market_configurations', COUNT(*) FROM market_configurations
    UNION ALL
    SELECT 'system_settings', COUNT(*) FROM system_settings
    ORDER BY table_name;
    " "Record counts after seeding"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    info "============================================"
    info "  Database Seed — ${PGDATABASE}"
    info "  Environment: ${ENVIRONMENT}"
    info "============================================"

    preflight
    seed_admin_user
    seed_risk_configs
    seed_strategies
    seed_market_config
    seed_system_settings
    verify_seed

    if [ "${DRY_RUN}" = false ]; then
        success "============================================"
        success "  Database Seeding Complete"
        success "============================================"
        info "Admin email: ${ADMIN_EMAIL}"
        if [ -n "${ADMIN_PASSWORD}" ]; then
            info "Admin password: ${ADMIN_PASSWORD}"
        fi
        warn "Change the admin password immediately after first login."
    else
        info "Dry run completed — no changes made"
    fi
}

main "$@"
