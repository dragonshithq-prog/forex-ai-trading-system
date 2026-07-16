#!/usr/bin/env bash
# =============================================================================
# Forex AI Trading Platform — Hetzner VPS One-Time Setup
# =============================================================================
# Run this ONCE on a fresh Ubuntu 24.04 Hetzner VPS:
#   ssh root@<YOUR_VPS_IP>
#   curl -fsSL https://raw.githubusercontent.com/.../setup-vps.sh | bash
#
# Or copy this file to the VPS and run:
#   chmod +x setup-vps.sh && ./setup-vps.sh
# =============================================================================
set -euo pipefail

echo "================================================"
echo "  Forex Trading Bot — VPS Setup"
echo "================================================"

# ── Update system ────────────────────────────────────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    ufw \
    git \
    make \
    openssl \
    fail2ban

# ── Install Docker ───────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo ">>> Installing Docker..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable --now docker
fi

# ── Install Docker Compose v2 ────────────────────────────────────────────────
if ! docker compose version &>/dev/null; then
    echo ">>> Installing Docker Compose..."
    DOCKER_CONFIG=${DOCKER_CONFIG:-/usr/local/lib/docker}
    mkdir -p "$DOCKER_CONFIG/cli-plugins"
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
    chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
fi

# ── Configure UFW Firewall ───────────────────────────────────────────────────
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh                # SSH
ufw allow 80/tcp             # HTTP  (Let's Encrypt ACME)
ufw allow 443/tcp            # HTTPS
ufw --force enable

# ── Configure fail2ban ───────────────────────────────────────────────────────
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
EOF
systemctl enable --now fail2ban

# ── Enable Docker BuildKit ───────────────────────────────────────────────────
cat >> /etc/environment << 'EOF'
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1
EOF

# ── Create deploy user ───────────────────────────────────────────────────────
if ! id -u deploy &>/dev/null; then
    useradd -m -s /bin/bash -G docker deploy
    echo ">>> Created 'deploy' user. Set a password:"
    passwd deploy
fi

# ── Set up swap (2GB) for safety ─────────────────────────────────────────────
if ! swapon --show | grep -q /swapfile; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo ">>> Swap enabled (2GB)"
fi

echo ""
echo "================================================"
echo "  ✅ VPS Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Clone the repo:"
echo "     git clone https://github.com/dragonshithq-prog/forex-ai-trading-system.git /home/deploy/app"
echo ""
echo "  2. Configure .env:"
echo "     cp deploy/.env.production /home/deploy/app/.env"
echo "     nano /home/deploy/app/.env"
echo ""
echo "  3. Run deploy:"
echo "     cd /home/deploy/app && bash deploy/deploy.sh"
echo ""
echo "  VPS IP: $(curl -4 -s ifconfig.me)"
echo "================================================"
