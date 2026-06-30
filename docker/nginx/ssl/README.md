# SSL Certificates Directory

This directory (`docker/nginx/ssl/`) is intentionally empty in version control.
**Never commit SSL private keys or certificates to git.**

## Required Files

Place the following files in this directory before starting nginx in production:

| File            | Description                                      |
|-----------------|--------------------------------------------------|
| `fullchain.pem` | Full certificate chain (cert + intermediates)    |
| `privkey.pem`   | Private key (mode 600, owned by root)            |
| `dhparam.pem`   | Diffie-Hellman parameters (optional, see below)  |

File permissions must be:
```bash
chmod 600 privkey.pem
chmod 644 fullchain.pem
chown root:root privkey.pem fullchain.pem
```

---

## Option A — Let's Encrypt (Recommended for Production)

Use [Certbot](https://certbot.eff.org/) with the webroot method (nginx handles
`.well-known/acme-challenge/` at port 80):

```bash
# Install certbot
sudo apt install certbot

# Obtain certificate (replace with your domain)
sudo certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  -d yourdomain.com \
  -d api.yourdomain.com \
  --email your@email.com \
  --agree-tos \
  --non-interactive

# Certificates are written to:
#   /etc/letsencrypt/live/yourdomain.com/fullchain.pem
#   /etc/letsencrypt/live/yourdomain.com/privkey.pem

# Copy (or symlink) to this directory
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./fullchain.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   ./privkey.pem
```

### Auto-Renewal Cron Job

```bash
# Add to root crontab (crontab -e)
0 3 * * * certbot renew --quiet --post-hook "docker compose -f /path/to/docker-compose.yml exec nginx nginx -s reload"
```

---

## Option B — Self-Signed (Development / Staging Only)

```bash
# Generate self-signed certificate (NOT for production)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out    fullchain.pem \
  -subj   "/C=US/ST=State/L=City/O=ForexTrading/CN=localhost"
```

---

## Option C — AWS Certificate Manager (ACM) with ALB

When using AWS ALB as the entry point, SSL termination is handled by ACM.
In that case, nginx runs without SSL (port 80 only, behind the ALB).
Comment out the SSL server block in `nginx.conf` and uncomment the
ALB-specific configuration.

---

## DH Parameters (Optional, Recommended)

```bash
# Generate 2048-bit DH params (takes a few minutes)
openssl dhparam -out dhparam.pem 2048
```

Then add to `nginx.conf` inside the SSL server block:
```nginx
ssl_dhparam /etc/nginx/ssl/dhparam.pem;
```

---

## .gitignore

The following `.gitignore` entry is already set in the root `.gitignore`:
```
docker/nginx/ssl/*.pem
docker/nginx/ssl/*.crt
docker/nginx/ssl/*.key
```
