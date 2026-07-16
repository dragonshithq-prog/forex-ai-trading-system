# Disaster Recovery Plan — Forex AI Trading Platform

> **Version:** 1.0.0  
> **Last Updated:** 2026-07-15  
> **Owner:** Platform Engineering  
> **RPO Target:** < 5 minutes  
> **RTO Target:** < 60 minutes (full stack)

---

## Table of Contents

1. [Recovery Objectives](#1-recovery-objectives)
2. [Service Dependencies & RPO/RTO](#2-service-dependencies--rporto)
3. [Backup Strategy](#3-backup-strategy)
4. [PostgreSQL Point-in-Time Recovery](#4-postgresql-point-in-time-recovery)
5. [Redis Restore Procedures](#5-redis-restore-procedures)
6. [Kafka Log Replay](#6-kafka-log-replay)
7. [Cross-Region Failover](#7-cross-region-failover)
8. [Runbooks](#8-runbooks)
9. [Validation](#9-validation)
10. [Appendices](#10-appendices)

---

## 1. Recovery Objectives

| Metric | Target | Measurement |
|--------|--------|-------------|
| **RPO (Recovery Point Objective)** | < 5 minutes | Maximum acceptable data loss |
| **RTO (Recovery Time Objective)** | < 60 minutes | Time to restore full trading |
| **RTO — Read-Only Mode** | < 10 minutes | Time to serve cached/static data |
| **RTO — DB Only** | < 30 minutes | Time to restore PostgreSQL |
| **RTO — Full Stack** | < 60 minutes | Time to restore all services |
| **Testing Cadence** | Monthly | Full DR drill every 30 days |

### Recovery Prioritization

```
Priority 1: Market data streaming (read-only, critical for traders)
Priority 2: Risk engine (must be operational before trading resumes)
Priority 3: Order execution (last to resume, requires risk validation)
Priority 4: Analytics & reporting (non-critical during recovery)
```

---

## 2. Service Dependencies & RPO/RTO

| Service | RPO | RTO | Failure Mode | Recovery Strategy |
|---------|-----|-----|-------------|-------------------|
| **PostgreSQL** | < 5 min | < 30 min | Primary failure, data corruption | WAL streaming → PITR → Standby promotion |
| **Redis** | < 1 min | < 5 min | Cluster loss, data flush | AOF replay → RDB reload |
| **Kafka** | < 5 min | < 15 min | Broker failure, partition loss | ISR catch-up → Log replay |
| **Application (Backend)** | N/A | < 5 min | Crash loop, OOM | K8s liveness probe → Rolling restart |
| **Application (Frontend)** | N/A | < 5 min | Static assets unavailable | CDN fallback → S3 static hosting |
| **Message Queue (RabbitMQ)** | < 10 min | < 15 min | Queue corruption | HA mirror → Queue recovery |
| **Prometheus** | < 1 hour | < 2 hours | Metrics loss | Thanos bucket replay |
| **S3 Buckets** | < 1 hour | < 30 min | Bucket deletion | Cross-region replication → Versioning |

### Dependency Graph

```
Traders / API Clients
    │
    ▼
┌─────────────┐     ┌──────────────┐
│  Backend API │────▶│  PostgreSQL  │
│  (FastAPI)   │     │  (Primary)   │
└──────┬──────┘     └──────┬───────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌──────────────┐
│   Redis     │     │   Kafka      │
│  (Cache)    │     │ (Event Bus)  │
└─────────────┘     └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  RabbitMQ    │
                    │ (Outbox)     │
                    └──────────────┘
```

---

## 3. Backup Strategy

### 3.1 PostgreSQL Backups

| Type | Frequency | Retention | Storage | Method |
|------|-----------|-----------|---------|--------|
| Full (pg_dump) | Daily | 30 days | S3 (`s3://backups/database/`) | `pg_dump -Fc` |
| WAL Archive | Continuous | 7 days | S3 + Local (`/wal_archive/`) | `archive_command` |
| Logical (schema) | Hourly | 7 days | S3 (`s3://backups/database/schema/`) | `pg_dump --schema-only` |

**Backup script (cron):**
```bash
# Daily full backup at 02:00 UTC
0 2 * * * pg_dump -Fc -h localhost -U forex forex_trading | \
    aws s3 cp - s3://forex-trading-backups/database/forex_trading_$(date +\%Y\%m\%d).dump

# WAL archiving (in postgresql.conf)
archive_command = 'aws s3 cp %p s3://forex-trading-backups/wal/%f && cp %p /wal_archive/%f'
```

### 3.2 Redis Backups

| Type | Frequency | Retention | Storage | Method |
|------|-----------|-----------|---------|--------|
| RDB Snapshot | Every 60 min | 7 days | S3 (`s3://backups/redis/`) | `SAVE` + `aws s3 cp` |
| AOF | Continuous | 24 hours | Local (`/var/lib/redis/aof/`) | `appendfsync everysec` |

**Backup validation:**
```bash
redis-check-rdb /var/lib/redis/dump.rdb
redis-check-aof /var/lib/redis/appendonly.aof
```

### 3.3 Kafka Backups

| Type | Frequency | Retention | Storage | Method |
|------|-----------|-----------|---------|--------|
| Consumer Offsets | Every 5 min | 7 days | S3 | `kafka-consumer-groups --describe` |
| Topic Data | Per retention | 7 days | Kafka log | `log.retention.hours=168` |
| Schema Registry | Daily | 30 days | S3 | `curl schema-registry:8081/subjects` |

### 3.4 Application & Config

| Type | Frequency | Retention | Storage |
|------|-----------|-----------|---------|
| K8s Manifests | Git push | Permanent | Git repo (infrastructure/) |
| Docker Images | Per build | 90 days | GHCR / ECR |
| Environment Config | Per change | Permanent | Vault / AWS Secrets Manager |
| SSL/TLS Certs | 30 days before expiry | 2 years | AWS Certificate Manager |

---

## 4. PostgreSQL Point-in-Time Recovery

### 4.1 Prerequisites

```bash
# Required tools
apt-get install postgresql-client wal-g
pip install awscli

# Verify WAL archiving is active
psql -c "SELECT pg_is_in_recovery();"
psql -c "SELECT * FROM pg_stat_archiver;"
```

### 4.2 Recovery Procedure

```bash
# 1. Identify the target recovery time
#    Check error logs, audit trail, or trading system alerts
TARGET_TIME="2026-07-14 14:30:00 UTC"

# 2. Find the latest full backup before the target time
LATEST_BACKUP=$(aws s3 ls s3://forex-trading-backups/database/ \
    | grep ".dump$" | sort | tail -1 | awk '{print $4}')

# 3. Run the disaster recovery script
./scripts/disaster-recovery.sh pitr "${TARGET_TIME}"

# 4. Verify recovery
psql -c "SELECT NOW() - pg_last_xact_replay_timestamp() AS replication_lag;"
psql -c "SELECT count(*) FROM trades WHERE created_at > '${TARGET_TIME}';"

# 5. Promote if recovery succeeded
pg_ctl promote -D /var/lib/postgresql/data
```

### 4.3 WAL Archive Recovery (Alternative)

If you have local WAL archives:

```bash
# 1. Restore base backup
pg_restore -Fc -d forex_trading latest_backup.dump

# 2. Configure recovery.conf (PostgreSQL < 12)
cat > /var/lib/postgresql/data/recovery.conf << EOF
restore_command = 'cp /wal_archive/%f %p'
recovery_target_time = '2026-07-14 14:30:00 UTC'
recovery_target_action = 'promote'
EOF

# For PostgreSQL >= 12, use:
# ALTER SYSTEM SET recovery_target_time = '2026-07-14 14:30:00 UTC';

# 3. Start PostgreSQL
pg_ctl start -D /var/lib/postgresql/data
```

### 4.4 Validation Steps

```sql
-- Check data integrity
SELECT count(*) FROM trades;
SELECT count(*) FROM positions;
SELECT count(*) FROM orders;

-- Verify no gaps in sequences
SELECT MAX(id) FROM trades;

-- Check referential integrity
SELECT count(*) FROM trades t
    LEFT JOIN positions p ON t.position_id = p.id
    WHERE p.id IS NULL;

-- Verify balances match expected
SELECT account_id, SUM(realized_pnl) FROM trades GROUP BY account_id;
```

---

## 5. Redis Restore Procedures

### 5.1 RDB Restore

```bash
# 1. Stop Redis
systemctl stop redis

# 2. Download latest RDB from S3
aws s3 cp s3://forex-trading-backups/redis/latest.rdb /var/lib/redis/dump.rdb

# 3. Validate RDB file
redis-check-rdb /var/lib/redis/dump.rdb

# 4. Set correct ownership
chown redis:redis /var/lib/redis/dump.rdb

# 5. Start Redis
systemctl start redis

# 6. Verify key count
redis-cli DBSIZE
```

### 5.2 AOF Replay

```bash
# 1. Download AOF from S3
aws s3 cp s3://forex-trading-backups/redis/aof/appendonly.aof /tmp/

# 2. Fix and validate AOF
redis-check-aof --fix /tmp/appendonly.aof

# 3. Replace current AOF
cp /tmp/appendonly.aof /var/lib/redis/appendonly.aof
chown redis:redis /var/lib/redis/appendonly.aof

# 4. Restart Redis with AOF
redis-cli CONFIG SET appendonly yes
systemctl restart redis
```

### 5.3 Key Validation

```bash
# Check expected keys exist
redis-cli KEYS "user:*" | wc -l
redis-cli KEYS "session:*" | wc -l
redis-cli KEYS "rate_limit:*" | wc -l

# Verify specific critical keys
redis-cli GET "config:risk:global"
redis-cli GET "auth:jwt:blacklist:*"
```

---

## 6. Kafka Log Replay

### 6.1 Consumer Group Reset

```bash
# 1. Stop the application consumers

# 2. Reset consumer group to replay from beginning
kafka-consumer-groups \
    --bootstrap-server localhost:9092 \
    --group forex-trading-backend \
    --topic trading.order \
    --reset-offsets \
    --to-earliest \
    --execute

# 3. Verify reset
kafka-consumer-groups \
    --bootstrap-server localhost:9092 \
    --group forex-trading-backend \
    --describe
```

### 6.2 Topic Replay via Script

```bash
# Replay trading orders
./scripts/disaster-recovery.sh kafka-replay trading.order

# Replay with custom consumer group and timestamp
GROUP_ID=forex-recovery-$(date +%s) \
REPLAY_MODE=from-timestamp \
REPLAY_TIMESTAMP="2026-07-14T14:00:00Z" \
    ./scripts/disaster-recovery.sh kafka-replay trading.deal
```

### 6.3 Outbox Replay

The transactional outbox pattern ensures no events are lost even during Kafka outages:

```bash
# 1. Verify pending outbox events
psql -d forex_trading -c "SELECT count(*) FROM outbox_events WHERE status = 'pending';"

# 2. Trigger replay via API
curl -X POST https://api.yourdomain.com/api/v1/system/outbox/replay

# 3. Monitor until pending count reaches zero
watch -n 5 "psql -d forex_trading -c 'SELECT status, count(*) FROM outbox_events GROUP BY status;'"
```

### 6.4 Data Consistency Check

```sql
-- Compare Kafka messages to DB transactions
-- This requires the Kafka message to include a correlation ID
SELECT
    o.correlation_id,
    o.status AS outbox_status,
    t.id AS trade_id
FROM outbox_events o
LEFT JOIN trades t ON o.correlation_id = t.correlation_id
WHERE o.status = 'published' AND t.id IS NULL;
```

---

## 7. Cross-Region Failover

### 7.1 Architecture

```
┌─────────────────────┐          ┌─────────────────────┐
│   us-east-1 (Primary│          │   us-west-2 (DR)    │
│                     │          │                      │
│  ┌───────────────┐  │          │  ┌───────────────┐   │
│  │  PostgreSQL   │──┼──────────┼──│ PostgreSQL RR │   │
│  │  (Primary)    │  │  WAL     │  │  (Standby)    │   │
│  └───────────────┘  │  Stream  │  └───────────────┘   │
│  ┌───────────────┐  │          │  ┌───────────────┐   │
│  │  Redis        │──┼──────────┼──│ Redis (Rep)   │   │
│  └───────────────┘  │  AOF     │  └───────────────┘   │
│  ┌───────────────┐  │  Sync    │  ┌───────────────┐   │
│  │  Kafka        │──┼──────────┼──│ Kafka (Mirror)│   │
│  └───────────────┘  │  MM2     │  └───────────────┘   │
│                     │          │  ┌───────────────┐   │
│  Route53 │          │          │  │  Backend API  │   │
│  api.yourdomain.com─┼──────────┼──│  (Scaled Up)  │   │
│                     │          │  └───────────────┘   │
└─────────────────────┘          └─────────────────────┘
```

### 7.2 Failover Trigger Conditions

Automatic failover is triggered when ANY of the following conditions are met:

1. **Primary DB unreachable** for > 30 seconds (health check timeout)
2. **Application error rate** exceeds 10% for 5 consecutive minutes
3. **Region-level outage** detected (AWS health dashboard)
4. **Data corruption** validated by automated integrity checks
5. **Manual trigger** by on-call engineer with admin approval

### 7.3 Failover Steps

```bash
# 1. Verify DR region readiness
kubectl config use-context forex-trading-dr
kubectl get pods -n forex-trading-production

# 2. Run failover script
./scripts/disaster-recovery.sh failover us-west-2

# 3. Promote PostgreSQL read replica to primary
aws rds promote-read-replica \
    --db-instance-identifier forex-trading-dr \
    --region us-west-2

# 4. Update Route53 DNS (TTL 60 seconds)
#    Points api.yourdomain.com → DR load balancer

# 5. Scale DR cluster to full capacity
kubectl scale deployment backend -n forex-trading-production --replicas=6
kubectl scale deployment frontend -n forex-trading-production --replicas=3

# 6. Verify all health checks pass
curl -sf https://api.yourdomain.com/health/ready | jq .
```

### 7.4 Failback Procedure

```bash
# 1. Once primary region is restored, set up reverse replication
# 2. Verify data consistency between regions
# 3. Run pre-failback checklist:
#    - Primary DB is healthy and caught up
#    - All Kafka topics have replicated
#    - Application image versions match

# 4. Switch DNS back to primary
# 5. Promote original primary DB
# 6. Validate production traffic flows correctly
```

---

## 8. Runbooks

### 8.1 Primary Database Failure

**Symptoms:** Health checks fail, `database` status is `error` in `/health/ready`

```
1. VERIFY:
   - Is the DB pod running? `kubectl get pods -n <ns> | grep postgres`
   - Is the PV/PVC intact? `kubectl get pvc -n <ns>`
   - Check logs: `kubectl logs -n <ns> deployment/postgres --tail=50`

2. ATTEMPT RESTART:
   - `kubectl rollout restart statefulset/postgres -n <ns>`

3. IF STILL DOWN → FAILOVER:
   - Promote DR replica (RDS: `aws rds promote-read-replica`)
   - Update DB connection string in backend config
   - Restart backend pods: `kubectl rollout restart deployment/backend -n <ns>`

4. RESTORE FROM BACKUP (if data corruption):
   - Run: `./scripts/disaster-recovery.sh restore-db <latest-backup>`

5. NOTIFY:
   - #incidents Slack channel
   - Update status page
```

### 8.2 Redis Cluster Loss

**Symptoms:** Cache misses spike, rate limiter disabled, session errors

```
1. CHECK:
   - Redis pod status: `kubectl get pods -n <ns> | grep redis`
   - Memory usage: `kubectl top pod -n <ns> | grep redis`

2. RESTART REDIS:
   - `kubectl rollout restart statefulset/redis -n <ns>`

3. IF DATA LOSS:
   - Restore from RDB: `./scripts/disaster-recovery.sh restore-redis`
   - Cold cache: Backend auto-populates on first request

4. VERIFY:
   - Rate limiter reconnects
   - Session cache warms up
```

### 8.3 Kafka Broker Failure

**Symptoms:** Outbox queue grows, event processing delayed

```
1. CHECK:
   - Broker pods: `kubectl get pods -n <ns> | grep kafka`
   - Topic health: `kafka-topics --describe --topic trading.order`

2. IF BROKER IS DOWN:
   - Check logs: `kubectl logs -n <ns> kafka-0 --tail=50`
   - Restart: `kubectl delete pod -n <ns> kafka-0`

3. IF PARTITION IS UNDER-REPLICATED:
   - Preferred leader election: `kafka-leader-election`

4. REPLAY PENDING EVENTS:
   - Trigger outbox relay: `curl -X POST /api/v1/system/outbox/replay`
   - Monitor: `psql -c "SELECT count(*) FROM outbox_events WHERE status = 'pending';"`
```

### 8.4 Application Crash Loop

**Symptoms:** Backend pod continuously restarting

```
1. CHECK:
   - Pod status: `kubectl get pods -n <ns> | grep backend`
   - Crash reason: `kubectl describe pod -n <ns> <pod-name>`
   - Logs: `kubectl logs -n <ns> <pod-name> --previous`

2. COMMON FIXES:
   - OOM: Increase memory limits
   - DB connection pool exhausted: Reduce pool size
   - Import error: Check image version
   - Config error: Validate environment variables

3. ROLLBACK (if caused by recent deploy):
   - `kubectl rollout undo deployment/backend -n <ns>`

4. SCALE UP:
   - Add replicas to spread load
   - `kubectl scale deployment/backend -n <ns> --replicas=8`
```

---

## 9. Validation

### 9.1 Monthly DR Drill Checklist

- [ ] Verify S3 backups exist and are restorable
- [ ] Test PostgreSQL restore on staging environment
- [ ] Test Redis RDB/AOF restore on staging
- [ ] Verify Kafka consumer offset backups
- [ ] Run cross-region failover drill (staging → DR)
- [ ] Validate RTO: full stack restore < 60 minutes
- [ ] Validate RPO: data loss < 5 minutes
- [ ] Update runbooks with lessons learned
- [ ] Update contact list and escalation paths
- [ ] Test outbox replay after simulated Kafka outage

### 9.2 Restore Testing

```bash
# Automated restore validation
./scripts/disaster-recovery.sh restore-db latest
./scripts/disaster-recovery.sh restore-redis
./scripts/validate-config.sh          # Validate restored configuration
./scripts/smoke-test.sh               # Smoke tests on restored system
```

### 9.3 Chaos Engineering

```bash
# Monthly chaos engineering to validate resilience
./scripts/chaos-test.sh --all

# Specific DR-related scenarios
./scripts/chaos-test.sh db_loss
./scripts/chaos-test.sh kafka_loss
./scripts/chaos-test.sh redis_down
./scripts/chaos-test.sh outbox_resilience
```

---

## 10. Appendices

### A. Emergency Contacts

| Role | Name | Phone | Email |
|------|------|-------|-------|
| On-Call Engineer | TBD | TBD | oncall@forex-trading.com |
| DB Admin | TBD | TBD | dba@forex-trading.com |
| Platform Lead | TBD | TBD | platform@forex-trading.com |
| Security Officer | TBD | TBD | security@forex-trading.com |

### B. Critical Dashboards

| Dashboard | URL | What to Check |
|-----------|-----|---------------|
| Application Health | `grafana.yourdomain.com/d/app-health` | Error rate, latency, throughput |
| Database | `grafana.yourdomain.com/d/postgres` | Connections, replication lag, WAL rate |
| Kafka | `grafana.yourdomain.com/d/kafka` | Consumer lag, partition count |
| Redis | `grafana.yourdomain.com/d/redis` | Memory usage, hit rate, connected clients |
| Infrastructure | `grafana.yourdomain.com/d/infra` | CPU, memory, disk, network |

### C. Related Documents

| Document | Location |
|----------|----------|
| Deployment Guide | `docs/DEPLOYMENT.md` |
| Architecture Overview | `docs/ARCHITECTURE.md` |
| Runbooks | `docs/runbooks/` |
| Security Policy | `docs/SECURITY.md` |

### D. Version History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-07-15 | 1.0.0 | Platform Eng | Initial disaster recovery plan |

---

> **Next DR Drill:** 2026-08-15  
> **Drill Coordinator:** On-Call Engineer (weekly rotation)
