# Deployment Guide — Forex AI Trading System

> **Version**: 0.1.0  
> **Last updated**: 2026-07-14

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Docker Deployment](#3-docker-deployment)
4. [Kubernetes Deployment](#4-kubernetes-deployment)
5. [Configuration](#5-configuration)
6. [Database Migrations](#6-database-migrations)
7. [Monitoring Setup](#7-monitoring-setup)
8. [Backup and Restore](#8-backup-and-restore)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

### Local Development

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Python | 3.12+ | Runtime |
| Node.js | 20+ | Frontend |
| Docker | 24+ | Containerization |
| Docker Compose | 2.24+ | Local orchestration |
| Git | 2.40+ | Version control |
| kubectl | 1.28+ | Kubernetes CLI (optional) |
| terraform | 1.7+ | Infrastructure as Code (optional) |
| helm | 3.14+ | Kubernetes package manager (optional) |

### Cloud (AWS)

| Service | Purpose |
|---------|---------|
| EKS (Kubernetes) | Container orchestration |
| RDS PostgreSQL | Managed database |
| ElastiCache Redis | Managed caching |
| MSK Kafka | Managed streaming |
| ECR | Container registry |
| S3 | Object storage |
| Secrets Manager | Secret storage |
| Route53 | DNS |
| ALB | Load balancing |
| WAF | Web application firewall |
| CloudWatch | Logging and monitoring |

---

## 2. Environment Setup

### 2.1 Clone and Configure

```bash
git clone https://github.com/your-org/forex-trading-system.git
cd forex-trading-system
cp .env.example .env
```

### 2.2 Generate Secrets

```bash
# Application secret
openssl rand -hex 32 >> .env  # Add as SECRET_KEY

# JWT signing key (RS256)
openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -pubout -in private.pem -out public.pem
# Set JWT_SECRET_KEY = contents of private.pem in .env

# Database password
openssl rand -base64 24  # Add as POSTGRES_PASSWORD

# Redis password
openssl rand -base64 24  # Add as REDIS_PASSWORD

# Grafana secret key
openssl rand -hex 32  # Add as GRAFANA_SECRET_KEY
```

### 2.3 Required Environment Variables

Minimum set required to start:

```dotenv
# Required
ENVIRONMENT=production
SECRET_KEY=<generated-32-byte-hex>
JWT_SECRET_KEY=<rsa-private-key-or-hs256-secret>
POSTGRES_PASSWORD=<generated-24-char-base64>
REDIS_PASSWORD=<generated-24-char-base64>
GRAFANA_ADMIN_PASSWORD=<strong-password>
GRAFANA_SECRET_KEY=<generated-32-byte-hex>
```

---

## 3. Docker Deployment

### 3.1 Build Images

```bash
# Build both images
make build

# Or build individually
make build-backend
make build-frontend

# With custom registry and tag
REGISTRY=ghcr.io/myorg IMAGE_TAG=v0.1.0 make build
```

### 3.2 Start Services

```bash
# Full stack
make up

# Individual services
docker compose -f docker/docker-compose.yml up -d postgres redis kafka
docker compose -f docker/docker-compose.yml up -d backend
docker compose -f docker/docker-compose.yml up -d frontend nginx
```

### 3.3 Verify Deployment

```bash
# Check all services
docker compose -f docker/docker-compose.yml ps

# Health check
curl http://localhost:8000/health

# Check logs
docker compose -f docker/docker-compose.yml logs -f backend
```

### 3.4 Scale Backend

```bash
# Scale to 3 replicas
docker compose -f docker/docker-compose.yml up -d --scale backend=3
```

### 3.5 Production Considerations

For production Docker deployments:

1. **Use a container registry**: Push images to ECR/ghcr.io and pull from there
2. **Set resource limits**: Already configured in `docker-compose.yml`
3. **Enable health checks**: Already configured for all services
4. **Configure logging driver**: Use `json-file` with rotation or CloudWatch
5. **Use secrets management**: Mount secrets from files, not environment variables
6. **TLS termination**: Configure Nginx with valid SSL certificates

---

## 4. Kubernetes Deployment

### 4.1 Prerequisites

```bash
# Create EKS cluster (or use existing)
terraform apply -auto-approve  # from infrastructure/

# Configure kubectl
aws eks update-kubeconfig --name forex-trading-cluster --region us-east-1

# Install external-secrets operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace

# Install ALB Ingress Controller
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=forex-trading-cluster
```

### 4.2 Deploy Infrastructure Components

```bash
# Namespace
kubectl apply -f infrastructure/k8s/namespace.yaml

# PostgreSQL (TimescaleDB)
kubectl apply -f infrastructure/k8s/postgres/

# Redis
kubectl apply -f infrastructure/k8s/redis/

# Kafka
kubectl apply -f infrastructure/k8s/kafka/

# Verify
kubectl -n forex-trading get pods -w
```

### 4.3 Deploy Backend

```bash
# Create secrets (edit infrastructure/k8s/backend/secrets.yaml first)
kubectl apply -f infrastructure/k8s/backend/secrets.yaml

# Deploy backend
kubectl apply -f infrastructure/k8s/backend/configmap.yaml
kubectl apply -f infrastructure/k8s/backend/deployment.yaml
kubectl apply -f infrastructure/k8s/backend/service.yaml

# Configure autoscaling
kubectl apply -f infrastructure/k8s/backend/hpa.yaml

# Configure pod disruption budget
kubectl apply -f infrastructure/k8s/backend/pdb.yaml
```

### 4.4 Deploy Frontend

```bash
kubectl apply -f infrastructure/k8s/frontend/
```

### 4.5 Deploy Monitoring

```bash
kubectl apply -f infrastructure/k8s/monitoring/
```

### 4.6 Configure Ingress

```bash
kubectl apply -f infrastructure/k8s/ingress.yaml
```

### 4.7 Verify Full Deployment

```bash
# Get all resources
kubectl -n forex-trading get all

# Check pods
kubectl -n forex-trading get pods -o wide

# Check ingress
kubectl -n forex-trading get ingress

# Test API
curl https://api.yourdomain.com/health

# Get backend logs
kubectl -n forex-trading logs -l app=backend --tail=100
```

### 4.8 Rolling Update

```bash
# Update image
kubectl -n forex-trading set image deployment/backend \
  backend=ghcr.io/myorg/forex-trading/backend:v0.1.1

# Monitor rollout
kubectl -n forex-trading rollout status deployment/backend

# Rollback if needed
kubectl -n forex-trading rollout undo deployment/backend
```

### 4.9 Autoscaling (HPA)

The backend has Horizontal Pod Autoscaling configured:

```yaml
# From infrastructure/k8s/backend/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
  namespace: forex-trading
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

---

## 5. Configuration

### 5.1 Configuration Layers

Configuration is resolved in this priority order:

1. **Environment variables** (highest priority)
2. **Kubernetes ConfigMap/Secrets** (when running in K8s)
3. **`.env` file** (development)
4. **Default values** in `Settings` class (lowest priority)

### 5.2 Kubernetes ConfigMap

```yaml
# infrastructure/k8s/backend/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-config
  namespace: forex-trading
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  WORKERS: "4"
  CORS_ORIGINS: "https://yourdomain.com"
  KAFKA_BOOTSTRAP_SERVERS: "kafka-service:9092"
```

### 5.3 Kubernetes Secrets

Secrets are loaded from AWS Secrets Manager via the external-secrets operator:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: backend-secrets
  namespace: forex-trading
spec:
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: backend-secrets
  data:
    - secretKey: SECRET_KEY
      remoteRef:
        key: forex-trading/secrets
        property: SECRET_KEY
    - secretKey: JWT_SECRET_KEY
      remoteRef:
        key: forex-trading/secrets
        property: JWT_SECRET_KEY
    - secretKey: POSTGRES_PASSWORD
      remoteRef:
        key: forex-trading/secrets
        property: POSTGRES_PASSWORD
    - secretKey: REDIS_PASSWORD
      remoteRef:
        key: forex-trading/secrets
        property: REDIS_PASSWORD
```

---

## 6. Database Migrations

### 6.1 Initial Setup

```bash
# Run all pending migrations
cd backend
alembic upgrade head
```

### 6.2 Creating Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "add_new_field_to_orders"

# Review the generated migration file in alembic/versions/
# Edit as needed to ensure correctness
```

### 6.3 Migration Commands

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade abc123def456

# Downgrade one revision
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade abc123def456

# View history
alembic history

# Show current revision
alembic current

# Check for pending migrations (without running)
alembic check
```

### 6.4 Production Migration Strategy

For production deployments, migrations run automatically as part of the CI/CD pipeline:

```yaml
# In CI/CD pipeline
jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run migrations
        run: |
          cd backend
          pip install -e ".[dev]"
          alembic upgrade head
        env:
          DATABASE_URL: ${{ secrets.PRODUCTION_DATABASE_URL }}
```

**Best practices:**
- Migrations run before the new application version is deployed
- Migrations must be backward-compatible (no breaking changes to existing data)
- Always test migrations on a staging database first
- Large migrations should use `batch` mode (for PostgreSQL ALTER TABLE)

---

## 7. Monitoring Setup

### 7.1 Prometheus

Prometheus is pre-configured with scrape targets for all services:

```yaml
# infrastructure/monitoring/prometheus.yml
scrape_configs:
  - job_name: forex-backend
    metrics_path: /metrics
    static_configs:
      - targets: ['backend:8000']
```

**Access:** http://localhost:9090 (development) or via ingress (production)

### 7.2 Grafana

Pre-built dashboards are auto-provisioned:

```bash
# Access Grafana
# Development: http://localhost:3001
# Production: https://monitoring.yourdomain.com

# Default login: admin / <GRAFANA_ADMIN_PASSWORD>
```

**Available Dashboards:**

| Dashboard | File | Description |
|-----------|------|-------------|
| Forex Overview | `forex_overview.json` | P&L, positions, win rate |
| AI Agents | `ai_agents.json` | Agent consensus, signal history |
| Risk Engine | `risk_engine.json` | Drawdown, circuit breaker status |
| System Health | `system_health.json` | API latency, error rates |

**Importing Dashboards:**
```
1. Grafana → + → Import
2. Upload JSON from infrastructure/monitoring/grafana/dashboards/
3. Select Prometheus data source
4. Import
```

### 7.3 Alerting

Alert rules are defined in `infrastructure/monitoring/alerts.yaml`:

| Alert | Threshold | Severity | Response |
|-------|-----------|----------|----------|
| `HighAPIErrorRate` | > 1% for 5m | Critical | Investigate immediately |
| `HighAPILatencyP95` | > 500ms for 5m | Warning | Check for bottlenecks |
| `CircuitBreakerActivated` | State = OPEN | Critical | Manual review required |
| `BackendPodsDown` | 0 pods for 2m | Critical | Emergency response |
| `DBConnectionPoolExhausted` | > 90% for 3m | Critical | Scale connections |
| `RedisDown` | Unreachable for 2m | Critical | Check Redis state |
| `AISignalGenerationStopped` | 0 signals in 15m | Warning | Check ML model service |
| `TradeExecutionFailureHigh` | > 5% for 3m | Critical | Check broker connectivity |

### 7.4 Distributed Tracing (Jaeger)

All API requests are traced via OpenTelemetry:

```bash
# Development Jaeger UI
# http://localhost:16686

# Search for traces by service, operation, tags, or time range
```

### 7.5 Log Aggregation

Logs are structured JSON, suitable for ingestion by:

- **CloudWatch** (AWS): Automatic if running on EKS with CloudWatch agent
- **ELK Stack**: Filebeat → Elasticsearch → Kibana
- **Loki**: Promtail → Loki → Grafana

Log format example:
```json
{
  "event": "request_completed",
  "request_id": "abc123",
  "method": "POST",
  "path": "/api/v1/trading/orders",
  "status_code": 201,
  "duration_ms": 45.2,
  "user_id": "uuid",
  "timestamp": "2026-07-14T14:30:00.123Z",
  "logger": "forex_trading.core.middleware",
  "level": "info"
}
```

---

## 8. Backup and Restore

### 8.1 Database Backup

#### Automated (via script)

```bash
# Backup to default location
make backup

# Or manually
./scripts/backup-db.sh ./backups/postgres
```

#### Manual (pg_dump)

```bash
# Full database backup
pg_dump -h localhost -U forex -d forex_trading \
  -F c -f ./backups/forex_trading_$(date +%Y%m%d_%H%M%S).dump

# Backup with compression
pg_dump -h localhost -U forex -d forex_trading \
  -F c -Z 9 -f ./backups/forex_trading_latest.dump
```

#### Docker Backup

```bash
docker exec forex_postgres pg_dump -U forex -d forex_trading \
  -F c > ./backups/forex_trading.dump
```

### 8.2 Database Restore

```bash
# Using pg_restore
pg_restore -h localhost -U forex -d forex_trading \
  -c -v ./backups/forex_trading_latest.dump

# Docker restore
cat ./backups/forex_trading.dump | docker exec -i forex_postgres \
  pg_restore -U forex -d forex_trading -c
```

### 8.3 S3 Backup Automation

For production, a CronJob handles regular backups to S3:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: db-backup
  namespace: forex-trading
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: pg-backup
              image: postgres:16
              command:
                - sh
                - -c
                - |
                  pg_dump -h postgres-service -U forex -d forex_trading -F c \
                    | aws s3 cp - s3://forex-trading-backups/db/$(date +%Y%m%d_%H%M%S).dump
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: postgres-secrets
                      key: POSTGRES_PASSWORD
```

### 8.4 Redis Backup

Redis AOF persistence is enabled by default (`appendonly yes`):

```bash
# Manual Redis save
docker exec forex_redis redis-cli -a $REDIS_PASSWORD SAVE

# Copy AOF file
docker cp forex_redis:/data/appendonly.aof ./backups/redis/
```

### 8.5 Backup Retention Policy

| Data | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| PostgreSQL full | Every 6 hours | 35 days | S3 + local |
| Redis AOF | Continuous | 7 days | Volume + S3 |
| Kafka logs | Continuous | 7 days | Volume |
| Configuration | Per deployment | Indefinite | Git + S3 |
| ML models | Per training | Indefinite | S3 |

---

## 9. Troubleshooting

### 9.1 Common Issues

#### "Database connection refused"

```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Verify connection string
echo $DATABASE_URL

# Test connectivity
docker compose exec backend nc -zv postgres 5432
```

**Solution:** Ensure PostgreSQL is healthy and `DATABASE_URL` has correct credentials.

#### "Redis connection error"

```bash
# Check Redis is running
docker compose ps redis

# Test Redis connection
docker compose exec redis redis-cli -a $REDIS_PASSWORD PING
```

**Solution:** Verify `REDIS_URL` format: `redis://:<password>@<host>:6379/0`

#### "Kafka broker not available"

```bash
# Check Kafka logs (KRaft initialization takes 30-60s)
docker compose logs kafka

# List topics
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

**Solution:** Wait for KRaft initialization. Check `KAFKA_BOOTSTRAP_SERVERS`.

#### "Alembic migration fails"

```bash
# Check migration history
cd backend
alembic history

# View current state
alembic current

# Run with SQL logging
DATABASE_ECHO=true alembic upgrade head
```

**Solution:** Ensure database exists and is accessible. Check `alembic_version` table for stale entries.

#### "Pod stuck in CrashLoopBackOff"

```bash
# Get pod details
kubectl -n forex-trading describe pod <pod-name>

# View logs
kubectl -n forex-trading logs <pod-name> --tail=100

# Check events
kubectl -n forex-trading get events --sort-by='.lastTimestamp'
```

**Common causes:**
- Missing secrets or ConfigMap
- Database not ready (init container failed)
- Resource limits too low
- Invalid configuration values

#### "HPA not scaling"

```bash
# Check HPA status
kubectl -n forex-trading get hpa backend-hpa -o wide

# Describe HPA
kubectl -n forex-trading describe hpa backend-hpa

# Check metrics server
kubectl -n kube-system get pods -l app=metrics-server
```

**Solution:** Ensure metrics-server is running and pods have resource requests configured.

### 9.2 Health Check Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | Simple liveness | `{"status": "healthy"}` |
| `GET /health/live` | K8s liveness probe | `{"status": "alive"}` |
| `GET /health/ready` | K8s readiness probe | `{"status": "ok", "checks": {...}}` |
| `GET /health/detailed` | Detailed health | Version & environment info |

### 9.3 Debug Mode

For development, enable debug mode:

```bash
ENVIRONMENT=development DEBUG=true uvicorn forex_trading.main:app --reload
```

This enables:
- Auto-reload on code changes
- Swagger UI at `/docs`
- Detailed error responses
- SQL query logging (if `DATABASE_ECHO=true`)
- In-memory token revocation (no Redis required for auth)

### 9.4 Reset Procedures

#### Reset Local Development

```bash
# Stop everything and remove volumes
docker compose -f docker/docker-compose.yml down -v

# Clean Python artifacts
make clean

# Rebuild
make build
make up

# Re-run migrations
make migrate
make seed
```

#### Reset Circuit Breaker

```bash
curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/reset \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"broker_account_id": "uuid", "reason": "Manual reset after review"}'
```

#### Emergency Stop (Kubernetes)

```bash
# Scale down all deployments
kubectl -n forex-trading scale deployment --all --replicas=0

# Or delete namespace
kubectl delete namespace forex-trading
```

### 9.5 Getting Help

```bash
# Run diagnosis
hermes doctor

# Collect logs
kubectl -n forex-trading logs -l app=backend --tail=1000 > backend-debug.log
kubectl -n forex-trading describe pods > pods-debug.txt

# Check resource usage
kubectl -n forex-trading top pods
kubectl -n forex-trading top nodes
```
