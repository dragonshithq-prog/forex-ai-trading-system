#!/usr/bin/env bash
# =============================================================================
# Forex AI Trading Platform — Deploy / Update Stack
# =============================================================================
# Usage:
#   bash deploy/deploy.sh              # First deploy
#   bash deploy/deploy.sh --ssl        # Deploy with Let's Encrypt SSL setup
#   bash deploy/deploy.sh --update     # Pull latest + rebuild + restart
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Check prerequisites ──────────────────────────────────────────────────────
check_prereqs() {
    if ! command -v docker &>/dev/null; then
        error "Docker not found. Run deploy/setup-vps.sh first."
        exit 1
    fi
    if ! docker compose version &>/dev/null; then
        error "Docker Compose not found. Run deploy/setup-vps.sh first."
        exit 1
    fi
    if [ ! -f .env ]; then
        error ".env file not found. Copy deploy/.env.production to .env and fill in values."
        exit 1
    fi
    # Source .env
    set -a; source .env; set +a
}

# ── Setup SSL via Let's Encrypt ──────────────────────────────────────────────
setup_ssl() {
    if [ -z "${DOMAIN:-}" ]; then
        error "DOMAIN not set in .env. Cannot setup SSL."
        exit 1
    fi

    info "Setting up SSL for $DOMAIN..."

    # Install certbot
    if ! command -v certbot &>/dev/null; then
        apt-get update && apt-get install -y certbot
    fi

    # Stop nginx temporarily to free port 80
    docker compose -f docker/docker-compose.yml stop nginx 2>/dev/null || true

    # Get certificate
    certbot certonly --standalone \
        -d "$DOMAIN" \
        -d "api.$DOMAIN" \
        -d "monitoring.$DOMAIN" \
        --email "admin@$DOMAIN" \
        --agree-tos \
        --non-interactive

    # Copy to nginx ssl directory
    cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" docker/nginx/ssl/
    cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem"   docker/nginx/ssl/
    chmod 600 docker/nginx/ssl/privkey.pem

    # Update nginx config with actual domain
    sed -i "s/server_name yourdomain.com api.yourdomain.com;/server_name $DOMAIN api.$DOMAIN;/g" docker/nginx/nginx.conf

    # Set up auto-renewal
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'cd $ROOT_DIR && docker compose -f docker/docker-compose.yml exec nginx nginx -s reload'") | crontab -

    info "SSL setup complete! Certificates auto-renew daily at 3 AM."
}

# ── Generate self-signed certs for initial deploy (no domain yet) ────────────
gen_selfsigned() {
    if [ ! -f docker/nginx/ssl/fullchain.pem ]; then
        warn "No SSL certs found. Generating self-signed certs for initial deploy."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout docker/nginx/ssl/privkey.pem \
            -out    docker/nginx/ssl/fullchain.pem \
            -subj "/C=US/ST=State/L=City/O=ForexTrading/CN=localhost" 2>/dev/null
    fi
}

# ── Deploy stack ─────────────────────────────────────────────────────────────
deploy_stack() {
    info "Building and starting Docker stack..."

    # Prepare directories
    mkdir -p docker/nginx/ssl docker/nginx/logs

    # Generate self-signed if no SSL certs yet
    gen_selfsigned

    # Build images from source
    info "Building backend image..."
    docker compose -f docker/docker-compose.yml build backend

    info "Building frontend image..."
    docker compose -f docker/docker-compose.yml build frontend

    # Start everything
    info "Starting all services..."
    docker compose -f docker/docker-compose.yml up -d

    info "Waiting for services to be healthy..."
    sleep 15
    docker compose -f docker/docker-compose.yml ps
}

# ── Update stack (pull latest + rebuild) ─────────────────────────────────────
update_stack() {
    info "Pulling latest code..."
    git pull

    info "Rebuilding and restarting..."
    deploy_stack
}

# ── Show status ──────────────────────────────────────────────────────────────
show_status() {
    echo ""
    echo "================================================"
    echo "  Service Status"
    echo "================================================"
    docker compose -f docker/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo "Logs:  docker compose -f docker/docker-compose.yml logs -f"
    echo ""
    if [ -n "${DOMAIN:-}" ]; then
        echo "  Dashboard:  https://$DOMAIN"
        echo "  API:        https://api.$DOMAIN"
        echo "  Monitoring: https://monitoring.$DOMAIN"
    else
        VPS_IP=$(curl -4 -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
        echo "  Dashboard:  http://$VPS_IP"
        echo "  (Set up SSL with: bash deploy/deploy.sh --ssl)"
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    check_prereqs

    case "${1:-}" in
        --ssl)
            setup_ssl
            deploy_stack
            show_status
            ;;
        --update)
            update_stack
            show_status
            ;;
        --status)
            show_status
            ;;
        *)
            deploy_stack
            show_status
            ;;
    esac
}

main "$@"
