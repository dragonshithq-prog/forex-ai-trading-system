# Deploy to Hetzner VPS

## Prerequisites

1. A Hetzner account (sign up at https://hetzner.com)
2. A domain name pointing to your VPS IP

## Step 1: Provision the VPS

1. Log into [Hetzner Cloud Console](https://console.hetzner.cloud)
2. Create a new project (or use existing)
3. Click **"Add Server"**
4. Choose:
   - **Location**: Your choice (Nuremberg/Falkenstein/Helsinki)
   - **Image**: Ubuntu 24.04 LTS
   - **Type**: CX22 (2 vCPU, 4GB RAM, 40GB SSD) — **$8.09/mo**
   - **SSH Keys**: Add your public key
   - **Firewall**: Create one allowing SSH (22), HTTP (80), HTTPS (443)
5. Click **"Create & Buy Now"**
6. Copy the IP address shown

## Step 2: Set up the VPS

```bash
# SSH into your VPS
ssh root@<YOUR_VPS_IP>

# Run the one-time setup (copies and runs setup script)
# Copy the setup-vps.sh file to the VPS first (from your local machine):
scp deploy/setup-vps.sh root@<YOUR_VPS_IP>:~
ssh root@<YOUR_VPS_IP>
chmod +x setup-vps.sh && ./setup-vps.sh
```

## Step 3: Configure DNS

In your domain registrar's DNS settings, create these A records:

| Type | Name              | Value          |
|------|-------------------|----------------|
| A    | `@`               | `<VPS_IP>`     |
| A    | `api`             | `<VPS_IP>`     |
| A    | `monitoring`      | `<VPS_IP>`     |

## Step 4: Deploy the App

```bash
# Still on the VPS as root — switch to deploy user
su - deploy

# Clone the repo
git clone https://github.com/dragonshithq-prog/forex-ai-trading-system.git app
cd app

# Configure environment
cp deploy/.env.production .env
nano .env   # Fill in all passwords and your domain

# Deploy with SSL
bash deploy/deploy.sh --ssl
```

Wait 2-3 minutes for the build. You'll see URLs at the end.

## Accessing the Stack

| Service    | URL                              |
|------------|----------------------------------|
| Dashboard  | `https://<YOUR_DOMAIN>`         |
| API        | `https://api.<YOUR_DOMAIN>`     |
| Monitoring | `https://monitoring.<YOUR_DOMAIN>` |

## Useful Commands

```bash
# View logs
docker compose -f docker/docker-compose.yml logs -f

# Check service status
docker compose -f docker/docker-compose.yml ps

# Restart a service
docker compose -f docker/docker-compose.yml restart backend

# Rebuild and update
bash deploy/deploy.sh --update

# SSH tunnel (if no domain yet)
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 root@<VPS_IP>
# Then open http://localhost:3000 in your browser
```

## Troubleshooting

**Build fails**: The CX22 has 4GB RAM. Docker builds sometimes need swap.
The setup script already enables 2GB swap. If builds still fail:
```bash
# Increase swap temporarily
swapoff /swapfile
fallocate -l 4G /swapfile
mkswap /swapfile
swapon /swapfile
```

**SSL fails**: Make sure DNS has propagated before running `--ssl`.
Check with: `dig +short <YOUR_DOMAIN>`
