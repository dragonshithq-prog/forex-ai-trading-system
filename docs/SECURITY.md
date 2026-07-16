# Security Guide — Forex AI Trading System

> **Version**: 0.1.0  
> **Last updated**: 2026-07-14

---

## Table of Contents

1. [Authentication Mechanisms](#1-authentication-mechanisms)
2. [Authorization Model (RBAC)](#2-authorization-model-rbac)
3. [API Key Management](#3-api-key-management)
4. [Rate Limiting](#4-rate-limiting)
5. [Audit Logging](#5-audit-logging)
6. [Secret Management](#6-secret-management)
7. [Security Headers](#7-security-headers)
8. [Token Management](#8-token-management)
9. [Network Security](#9-network-security)
10. [Incident Response Procedures](#10-incident-response-procedures)
11. [Security Checklist](#11-security-checklist)

---

## 1. Authentication Mechanisms

The system supports three authentication methods, each suited for different use cases.

### 1.1 JWT Bearer Tokens (Primary)

Used for all interactive API access via the web dashboard and mobile clients.

**Token Flow:**
```
┌──────────┐       ┌──────────┐       ┌──────────┐
│  Client  │ ──1──▶│  /login  │ ──2──▶│  JWT     │
│          │◀─3────│          │       │  Pair    │
└──────────┘       └──────────┘       └──────────┘
     │                                      │
     │  4. Access token (15 min)            │
     │  Authorization: Bearer <token>       │
     ▼                                      │
┌──────────┐                                │
│  API     │◀──── 5. Check expiry,          │
│  Gateway │    audience, revocation        │
└──────────┘                                │
                                            │
     ┌──────────────────────────────────────┘
     │  6. Refresh token rotation
     ▼
┌──────────┐       ┌──────────┐
│  Client  │ ──7──▶│ /refresh │
│          │◀─8────│          │
└──────────┘       └──────────┘
```

**Algorithm:**
- **Production**: RS256 (asymmetric RSA 2048-bit) — services verify with public key, only auth service holds private key
- **Development**: HS256 (symmetric HMAC) — simpler, single secret

**Token Claims:**
```json
{
  "sub": "user-uuid",
  "exp": 1790000000,
  "iat": 1700000000,
  "aud": "forex-trading:access",
  "iss": "forex-trading-bot",
  "role": "trader",
  "permissions": ["trade:execute", "position:read"],
  "mfa_verified": true,
  "token_type": "access",
  "jti": "unique-token-id"
}
```

**Validation:**
1. Signature verification (RS256 using public key)
2. Expiry check (`exp` claim)
3. Audience binding (access vs refresh tokens have different `aud` values)
4. Issuer validation (`iss` claim)
5. Token revocation check (Redis blacklist by `jti`)
6. Role and permission verification for protected endpoints

### 1.2 API Key Authentication (Programmatic)

Used for automated scripts, trading bots, and third-party integrations.

**Key Format:** `fx_key_<32-hex-characters>` (e.g., `fx_key_a1b2c3d4e5f6...`)

**Security Properties:**
- Keys are prefixed for easy identification in logs
- Only the SHA-256 hash of the secret portion is stored in the database
- The raw key is shown **exactly once** at creation
- Support rotation with a 5-minute grace period (configurable)

**Usage:**
```bash
curl -H "X-API-Key: fx_key_a1b2c3d4e5f6..." https://api.yourdomain.com/api/v1/trading/positions
```

### 1.3 Multi-Factor Authentication (MFA)

TOTP-based MFA via authenticator apps (Google Authenticator, Authy, etc.).

**Enrollment Flow:**
1. User requests MFA setup (requires password re-entry)
2. Server generates TOTP secret and 8 backup codes
3. QR code displayed for authenticator app scanning
4. User verifies with one TOTP code to confirm setup

**Backup Codes:**
- 8 codes generated per user
- Each code is single-use
- Stored as bcrypt hashes
- Can be regenerated (invalidates previous codes)

**Login with MFA:**
```
POST /auth/login  →  { mfa_required: true }
POST /auth/mfa/verify  →  { access_token, refresh_token }
```

---

## 2. Authorization Model (RBAC)

### 2.1 Roles

| Role | Description | Typical User |
|------|-------------|-------------|
| `viewer` | Read-only access to positions, orders, risk state, market data | Read-only API consumer |
| `trader` | Viewer + place/cancel orders, view AI signals | Active trader |
| `admin` | Trader + update risk config, reset circuit breaker, emergency close | Trading desk supervisor |
| `superadmin` | Admin + user management, system configuration, API key management | System administrator |

### 2.2 Permission Matrix

| Resource / Action | viewer | trader | admin | superadmin |
|------------------|--------|--------|-------|------------|
| **Market Data** | | | | |
| View symbols | ✅ | ✅ | ✅ | ✅ |
| View quotes | ✅ | ✅ | ✅ | ✅ |
| View candles | ✅ | ✅ | ✅ | ✅ |
| **Orders** | | | | |
| View own orders | ✅ | ✅ | ✅ | ✅ |
| Place order | ❌ | ✅ | ✅ | ✅ |
| Cancel order | ❌ | ✅ | ✅ | ✅ |
| Modify order | ❌ | ✅ | ✅ | ✅ |
| **Positions** | | | | |
| View own positions | ✅ | ✅ | ✅ | ✅ |
| Close position | ❌ | ✅ | ✅ | ✅ |
| Modify SL/TP | ❌ | ✅ | ✅ | ✅ |
| **Risk** | | | | |
| View risk state | ✅ | ✅ | ✅ | ✅ |
| View risk config | ✅ | ✅ | ✅ | ✅ |
| Update risk config | ❌ | ❌ | ✅ | ✅ |
| Reset circuit breaker | ❌ | ❌ | ✅ | ✅ |
| Emergency liquidate | ❌ | ❌ | ❌ | ✅ |
| **AI** | | | | |
| View decisions | ✅ | ✅ | ✅ | ✅ |
| View agent status | ✅ | ✅ | ✅ | ✅ |
| **Strategy** | | | | |
| View strategies | ✅ | ✅ | ✅ | ✅ |
| Modify strategy params | ❌ | ❌ | ✅ | ✅ |
| **Admin** | | | | |
| Manage users | ❌ | ❌ | ❌ | ✅ |
| View audit logs | ❌ | ❌ | ✅ | ✅ |
| Manage API keys | ❌ | ❌ | ✅ | ✅ |
| System config | ❌ | ❌ | ❌ | ✅ |

### 2.3 Permission Enforcement

Permissions are enforced at the API layer via dependency injection:

```python
from forex_trading.api.dependencies import require_role

@router.post("/risk/circuit-breaker/reset")
async def reset_circuit_breaker(
    request: Request,
    current_user: User = Depends(require_role("admin")),
):
    # Only accessible by admin or superadmin
    ...
```

---

## 3. API Key Management

### 3.1 Key Generation

```python
from forex_trading.shared.security.api_keys import ApiKeyManager

manager = ApiKeyManager()
material = manager.generate_api_key()
# material.raw_key:   "fx_key_a1b2c3d4e5f67890abcdef1234567890"
# material.key_hash:  "<sha256-hex-digest>"
# material.key_prefix: "fx_key_a1b2c3d4"
```

### 3.2 Key Storage

Only the SHA-256 hash is stored in the database:
```sql
-- Never store the raw key
INSERT INTO api_keys (user_id, key_hash, key_prefix, name, expires_at)
VALUES ('uuid', 'sha256-hex-digest', 'fx_key_a1b2c3d4', 'Trading Bot', NULL);
```

### 3.3 Key Verification

```python
def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    secret = raw_key[len(KEY_PREFIX):]  # Remove prefix
    computed = hashlib.sha256(secret.encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)
```

### 3.4 Key Rotation

Keys support rotation with a grace period:
1. Generate new key → add to database alongside old key
2. Both keys valid for 5 minutes (configurable grace period)
3. After grace period, old key is removed
4. New raw key shown once to the caller

---

## 4. Rate Limiting

### 4.1 Architecture

Sliding window rate limiter backed by Redis:

```
Client IP/User/API Key
         │
         ▼
┌────────────────────┐
│   Rate Limit Rule   │
│  route, max_reqs,  │
│  window_seconds    │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Redis Sliding     │
│  Window Counter    │
│  (sorted set)      │
└────────┬───────────┘
         │
    ┌────┴────┐
    │         │
   <limit    ≥limit
    │         │
    ▼         ▼
  Allow    429 Too Many
           + Retry-After
```

### 4.2 Default Rules

| Route Pattern | Max Requests | Window | Scope | 
|--------------|-------------|--------|-------|
| `/api/v1/auth/login` | 10 | 60s | Per IP |
| `/api/v1/auth/register` | 5 | 60s | Per IP |
| `/api/v1/auth/*` | 20 | 60s | Per IP + Per User |
| `/api/v1/trading/*` | 60 | 60s | Per IP + Per User + Per API Key |
| `/api/v1/risk/*` | 30 | 60s | Per IP + Per User + Per API Key |
| `/api/v1/market/*` | 120 | 60s | Per IP + Per User + Per API Key |
| `/api/v1/*` (default) | 100 | 60s | Per IP + Per User + Per API Key |

### 4.3 Response Headers

```
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1626270000
Content-Type: application/json

{
  "detail": "Rate limit exceeded. Try again in 45 seconds.",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after_seconds": 45
}
```

### 4.4 Graceful Degradation

If Redis is unavailable, rate limiting degrades gracefully:
- Logs a warning at startup
- Allows requests through without rate limiting (best effort)
- All other system functions continue normally

---

## 5. Audit Logging

### 5.1 Overview

Every sensitive operation is immutably logged to the `audit_logs` table. The audit system captures:

1. **All API requests** (via middleware) — method, path, status, user, IP
2. **Specific sensitive actions** (via explicit audit service calls)

### 5.2 Sensitive Actions

The following action categories are always audited:

| Category | Actions |
|----------|---------|
| **Authentication** | `user.login`, `user.logout`, `user.password.reset`, `user.password.change` |
| **User Management** | `user.create`, `user.delete`, `user.role.update`, `user.toggle_active` |
| **MFA** | `user.mfa.setup`, `user.mfa.verify`, `user.mfa.disable` |
| **Broker Accounts** | `broker.account.create`, `broker.account.update`, `broker.account.delete` |
| **Risk Configuration** | `risk.config.update`, `risk.circuit_breaker.reset` |
| **Trading Overrides** | `trading.override.close`, `trading.emergency.liquidate` |
| **API Keys** | `api_key.create`, `api_key.revoke`, `api_key.rotate` |

### 5.3 Audit Log Schema

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,       -- e.g., "risk.config.update"
    resource_type VARCHAR(50),           -- e.g., "risk_config"
    resource_id UUID,                    -- affected resource UUID
    details JSONB,                       -- contextual payload
    ip_address INET,
    user_agent TEXT,
    request_id UUID,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    -- Index for fast lookup
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
```

### 5.4 Immutability

The `audit_logs` table is **append-only**. An PostgreSQL trigger prevents UPDATE and DELETE operations:

```sql
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: mutations are not allowed';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_audit_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

CREATE TRIGGER trg_prevent_audit_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
```

### 5.5 Audit Middleware

A FastAPI middleware captures all API requests:

```python
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if self._is_sensitive(request.method, request.url.path):
            await audit_service.log(
                action=f"{request.method}.{request.url.path}",
                user_id=getattr(request.state, "user_id", None),
                ip_address=request.client.host,
                details={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status": response.status_code,
                }
            )
        return response
```

---

## 6. Secret Management

### 6.1 Development (.env)

In development, secrets are stored in a `.env` file at the project root:

```dotenv
# NEVER commit .env to version control
SECRET_KEY=development-secret-key
JWT_SECRET_KEY=development-jwt-secret
POSTGRES_PASSWORD=dev-db-password
REDIS_PASSWORD=dev-redis-password
```

### 6.2 Production (AWS Secrets Manager)

In production, all secrets are stored in **AWS Secrets Manager** with automatic rotation:

| Secret Name | Contains | Rotation |
|-------------|----------|----------|
| `forex-trading/jwt/private-key` | RSA private key for JWT signing | Every 90 days |
| `forex-trading/jwt/public-key` | RSA public key for JWT verification | Every 90 days |
| `forex-trading/database` | `POSTGRES_PASSWORD`, connection strings | Every 180 days |
| `forex-trading/redis` | `REDIS_PASSWORD` | Every 180 days |
| `forex-trading/broker/oanda` | OANDA API key and account ID | On-demand |
| `forex-trading/grafana` | Grafana admin password and secret key | Every 90 days |

### 6.3 Kubernetes Secrets

For Kubernetes deployments, secrets are stored in `Secrets` objects (with external-secrets operator for production):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: backend-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: backend-secrets
  data:
    - secretKey: JWT_SECRET_KEY
      remoteRef:
        key: forex-trading/jwt/private-key
```

### 6.4 Secret Validation

At startup, `validate_production_settings()` performs a fail-fast check:

```python
def validate_production_settings():
    secrets = get_secrets_settings()
    if settings.is_production:
        if not secrets.JWT_SECRET_KEY or secrets.JWT_SECRET_KEY.startswith("dev-"):
            raise RuntimeError("Production JWT secret not configured")
        if not secrets.SECRET_KEY or secrets.SECRET_KEY.startswith("dev-"):
            raise RuntimeError("Production SECRET_KEY not configured")
```

### 6.5 Fernet Credential Encryption

Broker credentials (API keys, passwords) are encrypted at rest using **Fernet** symmetric encryption:

```python
from forex_trading.core.security import encrypt_credentials, decrypt_credentials

# Storing
encrypted = encrypt_credentials({"api_key": "oanda-key-123", "account_id": "001-001"})
# Store 'encrypted' in the database

# Retrieving
credentials = decrypt_credentials(encrypted)
# Use credentials['api_key'], credentials['account_id']
```

The Fernet key is derived from `SECRET_KEY` via SHA-256, ensuring it's never hardcoded.

---

## 7. Security Headers

Every API response includes the following security headers (enforced via middleware):

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing |
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Enables XSS filter |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Enforces HTTPS (2 years) |
| `Content-Security-Policy` | `default-src 'self'; ...` | Restricts resource origins |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disables unused browser features |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Controls referrer header |
| `Cache-Control` | `no-store, no-cache, must-revalidate` | Prevents caching of sensitive data |

---

## 8. Token Management

### 8.1 Token Lifecycle

```
                    ┌─────────────────────┐
                    │   User Login        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Token Pair Issued  │
                    │  access (15min)     │
                    │  refresh (24hr)     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │ Access token │ │ Refresh      │ │ Token        │
      │ valid, use   │ │ token valid  │ │ expires      │
      │ for API calls │ │ -> /refresh  │ │ -> re-login  │
      └──────────────┘ └──────────────┘ └──────────────┘
              │                │
              ▼                ▼
      ┌──────────────┐ ┌──────────────┐
      │ Expires after │ │ Rotation:    │
      │ 15 minutes    │ │ old revoked  │
      │               │ │ new pair     │
      └──────────────┘ └──────────────┘
```

### 8.2 Token Revocation

Tokens are revoked via a Redis-backed blacklist keyed by JWT ID (`jti`):

| Operation | Revocation |
|-----------|------------|
| User logout | Refresh token `jti` added to blacklist |
| Password change | All user tokens revoked |
| MFA disable | All user tokens revoked |
| Admin force-logout | Specific user tokens revoked |
| Token refresh | Old refresh token `jti` revoked |

### 8.3 Token Storage (Client)

**Web Dashboard:** Access token stored in memory only (not localStorage). Refresh token stored in httpOnly, Secure, SameSite=Strict cookie.

**API Clients:** Tokens should be stored in environment variables or a secrets manager. Never hardcode tokens in source code.

---

## 9. Network Security

### 9.1 Docker Network Isolation (3-Tier)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INTERNET                                      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                    ┌───────▼───────┐
                    │  Nginx (DMZ)  │  Ports 80/443
                    │  frontend_net │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
     ┌────────▼──────┐     │    ┌────────▼──────┐
     │  Frontend     │     │    │  Backend API  │
     │  (Next.js)    │     │    │  (FastAPI)    │
     │  frontend_net │     │    │  dual-homed   │
     └───────────────┘     │    └───────┬───────┘
                           │            │
                           │    ┌───────▼───────┐
                           │    │  backend_net  │
                           │    │  (internal)   │
                           │    └───────┬───────┘
                           │            │
                           │    ┌───────▼───────┐
                           │    │   Kafka       │
                           │    │   Prometheus  │
                           │    │   Grafana     │
                           │    └───────────────┘
                           │
                    ┌───────▼───────┐
                    │  db_network   │  (internal, no internet)
                    │  PostgreSQL   │
                    │  Redis        │
                    └───────────────┘
```

**Security properties:**
- Database tier (`db_network`) has **no external internet access** (`internal: true`)
- App tier (`backend_network`) has **no external internet access** (`internal: true`)
- Only the frontend network (`frontend_network`) is internet-facing (DMZ)
- The backend is dual-homed, bridging frontend and app tiers — the **only** bridge
- Database ports are bound to `127.0.0.1` only (not exposed to Docker networks beyond what's needed)

### 9.2 Transport Security

- **TLS 1.3** for all external communications (HTTPS, WSS)
- **mTLS** for inter-service communication in Kubernetes (service mesh)
- Internal Redis/PostgreSQL connections are not TLS-terminated by default (network isolation provides protection), but can be enabled for compliance

### 9.3 Firewall Rules

| Source | Destination | Port | Protocol | Purpose |
|--------|-------------|------|----------|---------|
| Internet | Nginx | 80/443 | TCP | HTTP/HTTPS |
| Nginx | Frontend | 3000 | TCP | Reverse proxy |
| Nginx | Backend | 8000 | TCP | API proxy |
| Backend | PostgreSQL | 5432 | TCP | Database |
| Backend | Redis | 6379 | TCP | Cache |
| Backend | Kafka | 9092 | TCP | Messaging |
| Backend | Prometheus | 9090 | TCP | Metrics |
| Prometheus | Backend | 8000 | TCP | Metrics scrape |
| Grafana | Prometheus | 9090 | TCP | Data source |

---

## 10. Incident Response Procedures

### 10.1 Severity Levels

| Level | Definition | Response Time | Example |
|-------|-----------|---------------|---------|
| **SEV-1** | Critical — system down, data breach, unauthorized trading | < 15 minutes | Circuit breaker bypass, database breach |
| **SEV-2** | High — major feature unavailable, security anomaly | < 1 hour | Rate limiting bypass, audit log tampering |
| **SEV-3** | Medium — partial degradation, non-critical security issue | < 4 hours | Suspicious login pattern, expired TLS cert |
| **SEV-4** | Low — cosmetic, informational | < 24 hours | Minor security header issue, stale API key |

### 10.2 Response Runbook

#### SEV-1: Suspected Security Breach

1. **IMMEDIATELY** activate circuit breaker (disables all trading):
   ```bash
   curl -X POST https://api.yourdomain.com/api/v1/risk/emergency-liquidate \
     -H "Authorization: Bearer <admin-token>" \
     -d '{"broker_account_id": "all", "reason": "Security incident — SEV-1", "confirm": true}'
   ```

2. **Revoke all active tokens:**
   ```bash
   # Redis flush (with caution — confirms impact)
   redis-cli -a $REDIS_PASSWORD FLUSHALL
   ```

3. **Rotate all secrets** in AWS Secrets Manager

4. **Isolate affected instances** in Kubernetes:
   ```bash
   kubectl -n forex-trading scale deployment backend --replicas=0
   ```

5. **Preserve forensic data:**
   ```bash
   kubectl -n forex-trading logs --tail=10000 -l app=backend > forensic-logs.txt
   ```

6. **Notify** the security team and begin post-mortem

#### SEV-2: Authentication Anomaly

1. Check rate limit logs for brute force patterns:
   ```sql
   SELECT * FROM audit_logs 
   WHERE action = 'user.login' AND timestamp > NOW() - INTERVAL '1 hour'
   ORDER BY timestamp DESC;
   ```

2. Review failed authentication attempts by IP:
   ```sql
   SELECT ip_address, COUNT(*) as attempts 
   FROM audit_logs 
   WHERE action = 'user.login' AND details->>'status' = '401'
   GROUP BY ip_address HAVING COUNT(*) > 10;
   ```

3. Temporarily block suspicious IPs:
   ```python
   # Add IP to deny list in Redis
   await redis.set(f"blocked:ip:{suspicious_ip}", "1", ex=3600)
   ```

4. Force password reset for affected accounts

#### SEV-3: Certificate Expiry

1. Check certificate expiry:
   ```bash
   openssl s_client -connect api.yourdomain.com:443 -servername api.yourdomain.com </dev/null 2>/dev/null | openssl x509 -noout -dates
   ```

2. Renew via cert-manager (if using Let's Encrypt) or upload new certificate

3. Verify after renewal:
   ```bash
   curl -vI https://api.yourdomain.com/health
   ```

### 10.3 Post-Mortem Process

1. **Timeline**: Document exact sequence of events
2. **Root cause**: Identify the underlying vulnerability or failure
3. **Impact assessment**: Quantify data exposure, financial loss, downtime
4. **Corrective actions**: Implement fixes and preventive measures
5. **Lessons learned**: Update runbooks, security policies, monitoring

---

## 11. Security Checklist

### Pre-Production

- [ ] `ENVIRONMENT=production` and `DEBUG=false`
- [ ] RSA-2048 key pair generated for JWT (not HS256)
- [ ] All secrets stored in AWS Secrets Manager (not `.env`)
- [ ] Database passwords meet complexity requirements (> 20 chars)
- [ ] `CORS_ORIGINS` set to specific production domain(s)
- [ ] `TrustedHostMiddleware` configured with production domain
- [ ] TLS certificates installed and auto-renewal configured
- [ ] Rate limiting rules reviewed and tuned for expected load
- [ ] Audit logging verified for all sensitive actions
- [ ] Network isolation verified (DB tier has no internet access)
- [ ] Docker containers use `read_only: true` and `no-new-privileges: true`
- [ ] Container images scanned for vulnerabilities (Trivy)
- [ ] Dependency vulnerabilities checked (Dependabot)
- [ ] WAF rules configured (rate limiting, SQLi, XSS)
- [ ] Backup and disaster recovery procedures tested

### Regular Audits

- [ ] Review audit logs for suspicious activity (weekly)
- [ ] Rotate JWT signing keys (every 90 days)
- [ ] Rotate database passwords (every 180 days)
- [ ] Review API key usage and revoke unused keys (monthly)
- [ ] Update dependencies and apply security patches (weekly)
- [ ] Run penetration tests (quarterly)
- [ ] Review and update incident response runbooks (quarterly)
- [ ] Verify backup integrity and restore procedures (monthly)
- [ ] Review IAM roles and permissions (quarterly)
- [ ] Check TLS certificate expiry (weekly)
