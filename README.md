# Forex AI Trading System

[![CI Pipeline](https://github.com/your-org/forex-trading-system/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/forex-trading-system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)

**Institutional-grade, autonomous AI Forex trading ecosystem** built with Clean Architecture, Domain-Driven Design, and Event-Driven principles. Capital preservation first, profit generation second.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE LAYER                              │
│              ┌──────────┐  ┌──────────┐  ┌───────────────────────┐      │
│              │ Next.js  │  │ Grafana  │  │ API Clients (REST/WS) │      │
│              │ Dashboard│  │ Dashboards│  │                       │      │
│              └────┬─────┘  └──────────┘  └───────────┬───────────┘      │
└───────────────────┼──────────────────────────────────┼───────────────────┘
                    │           API Gateway             │
                    │   FastAPI + Rate Limiting + Auth  │
┌───────────────────▼──────────────────────────────────▼───────────────────┐
│                      ORCHESTRATION & MESSAGE BUS                          │
│          Kafka (Event Stream)   │   RabbitMQ (Commands)                    │
└─────┬──────────┬──────────┬─────┴──────┬──────────┬──────────┬──────────┘
      │          │          │            │          │          │
      ▼          ▼          ▼            ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Market  │ │   AI    │ │Strategy│ │  Risk   │ │Execution│ │ Broker  │
│  Data   │ │Orchestra│ │ Engine │ │ Engine  │ │ Engine  │ │ Gateway │
│ Service │ │  tor    │ │        │ │(Auth.)  │ │         │ │ Plugin  │
└────┬────┘ └────┬────┘ └───┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
     │           │          │           │           │           │
     └───────────┴──────────┴───────────┴───────────┴───────────┘
                                      │
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                         DATA & PERSISTENCE LAYER                           │
│  ┌───────────┐  ┌─────────────┐  ┌───────────┐  ┌───────────────────┐   │
│  │PostgreSQL │  │ TimescaleDB │  │   Redis   │  │   S3 / MinIO      │   │
│  │ (OLTP)    │  │ (Time-Series)│  │ (Cache/PubSub)│ (Models/Reports)│   │
│  └───────────┘  └─────────────┘  └───────────┘  └───────────────────┘   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Design principles:**
- **Risk-First**: Every subsystem has a risk gate; the Risk Engine has absolute override authority
- **Explainability**: Every decision produces an audit trail with confidence scores and rationale
- **Modularity**: Clean Architecture boundaries; each component independently testable and deployable
- **Resilience**: Graceful degradation; no single point of failure can halt the system
- **Observability**: Full distributed tracing, metrics, and centralized logging from day one
- **Security by Default**: Zero-trust internal networking, encrypted secrets, RBAC on all endpoints

---

## Quick Start (5 Steps)

### Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.12+ | pyenv or .venv recommended |
| Node.js | 20+ | npm 10+ |
| Docker & Docker Compose | 24+ | For local services |
| PostgreSQL | 16+ (TimescaleDB) | Or use Docker Compose |
| Redis | 7+ | Or use Docker Compose |
| Apache Kafka | 3.5+ | Or use Docker Compose |
| Git | 2.x | |

### Step 1: Clone and Configure

```bash
git clone https://github.com/your-org/forex-trading-system.git
cd forex-trading-system
cp .env.example .env
# Edit .env with your secrets (see Configuration Reference below)
```

### Step 2: Start Infrastructure Services

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis kafka
```

This starts PostgreSQL 16 (TimescaleDB), Redis 7, and Kafka 3.x in KRaft mode. Wait for all health checks to pass:

```bash
docker compose -f docker/docker-compose.yml ps
```

### Step 3: Setup Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"

# Run database migrations
alembic upgrade head
```

### Step 4: Setup Frontend (Optional)

```bash
cd frontend
npm install
```

### Step 5: Run the System

```bash
# Backend (Terminal 1)
cd backend
uvicorn forex_trading.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (Terminal 2, optional)
cd frontend
npm run dev
```

**Verify it works:**
```bash
curl http://localhost:8000/health
# → {"status":"healthy","version":"0.1.0"}
```

Open the interactive API docs: http://localhost:8000/docs

---

## Using Docker Compose (Full Stack)

```bash
# Start everything
docker compose -f docker/docker-compose.yml up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f backend

# Stop everything
docker compose -f docker/docker-compose.yml down

# Stop and remove volumes (data loss!)
docker compose -f docker/docker-compose.yml down -v
```

| Service | URL / Port | Access |
|---------|-----------|--------|
| API | http://localhost:8000 | Public |
| PostgreSQL | localhost:5432 | Localhost only |
| Redis | localhost:6379 | Localhost only |
| Kafka | localhost:9092 | Localhost only |
| Grafana | http://localhost:3001 | Admin: admin |
| Prometheus | http://localhost:9090 | Internal |
| Flower (Celery) | http://localhost:5555 | Admin auth |

---

## Configuration Reference

### Core Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_NAME` | No | `Forex AI Trading System` | Application name |
| `ENVIRONMENT` | Yes | `development` | `development`, `staging`, `production`, `testing` |
| `SECRET_KEY` | **Yes** | — | App encryption key: `openssl rand -hex 32` |
| `DEBUG` | No | `true` | Enable debug mode (set `false` in production) |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8000` | Server port |
| `API_PREFIX` | No | `/api/v1` | API version prefix |
| `WORKERS` | No | `4` | Gunicorn worker count |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | No | `json` | `json` or `console` |

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | `sqlite+aiosqlite:///./forex_trading.db` | PostgreSQL connection string (use asyncpg in production) |
| `POSTGRES_DB` | Yes | `forex_trading` | PostgreSQL database name |
| `POSTGRES_USER` | Yes | `forex` | PostgreSQL user |
| `POSTGRES_PASSWORD` | **Yes** | — | PostgreSQL password: `openssl rand -base64 24` |
| `DATABASE_POOL_SIZE` | No | `20` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | No | `10` | Max overflow connections |
| `DATABASE_ECHO` | No | `false` | Log all SQL (dev only) |

### Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | **Yes** | `redis://localhost:6379/0` | Redis connection string |
| `REDIS_PASSWORD` | **Yes** | — | Redis password: `openssl rand -base64 24` |
| `REDIS_MAX_CONNECTIONS` | No | `50` | Max Redis connections |

### JWT Authentication

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET_KEY` | **Yes** | — | HMAC secret or RSA private key: `openssl rand -hex 64` |
| `JWT_ALGORITHM` | No | `RS256` | `HS256` (dev) or `RS256` (production — asymmetric) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Access token TTL (short) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token TTL |

### Risk Management

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAX_POSITION_SIZE_PCT` | No | `2.0` | Max position as % of equity |
| `MAX_TOTAL_EXPOSURE_PCT` | No | `20.0` | Max total exposure as % of equity |
| `MAX_DRAWDOWN_DAILY_PCT` | No | `3.0` | Daily drawdown warning limit |
| `MAX_DRAWDOWN_WEEKLY_PCT` | No | `5.0` | Weekly drawdown warning limit |
| `MAX_DRAWDOWN_MONTHLY_PCT` | No | `10.0` | Monthly drawdown warning limit |
| `MAX_DRAWDOWN_TOTAL_PCT` | No | `15.0` | Hard circuit breaker limit |
| `MAX_POSITIONS` | No | `10` | Max concurrent open positions |
| `RISK_PER_TRADE_PCT` | No | `1.0` | Risk per trade as % of account |

### AI / ML

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AI_MIN_AGENTS` | No | `4` | Minimum agents for consensus |
| `AI_MIN_AGREEMENT_THRESHOLD` | No | `0.60` | Minimum weighted agreement (0.0–1.0) |
| `AI_MAX_CONFLICT_THRESHOLD` | No | `0.30` | Maximum allowed conflict (0.0–1.0) |
| `AI_MODEL_PATH` | No | `./ml/artifacts` | ML model storage path |

### Kafka (Message Bus)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | No | `kafka:9092` | Kafka broker list |
| `KAFKA_CLUSTER_ID` | No | `MkU3OEVBNTcwNTJENDM2Qk` | KRaft cluster ID |
| `KAFKA_NUM_PARTITIONS` | No | `6` | Default partition count |
| `KAFKA_REPLICATION_FACTOR` | No | `1` | Default replication |

### Broker Integration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OANDA_API_KEY` | For OANDA | — | OANDA v20 REST API key |
| `OANDA_ACCOUNT_ID` | For OANDA | — | OANDA account identifier |
| `OANDA_ENVIRONMENT` | No | `practice` | `practice` or `live` |
| `MT5_ACCOUNT_NUMBER` | For MT5 | — | MetaTrader 5 account number |
| `MT5_PASSWORD` | For MT5 | — | MT5 account password |
| `MT5_SERVER` | For MT5 | — | MT5 broker server |
| `MT4_HOST` | No | `localhost` | MT4 bridge host |
| `MT4_PORT` | No | `3000` | MT4 bridge port |

### Monitoring

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROMETHEUS_ENABLED` | No | `true` | Enable Prometheus metrics |
| `PROMETHEUS_PORT` | No | `8000` | Metrics endpoint port |
| `JAEGER_ENDPOINT` | No | `http://localhost:14268/api/traces` | Jaeger collector endpoint |
| `OTEL_SERVICE_NAME` | No | `forex-trading-backend` | OpenTelemetry service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `http://localhost:4317` | OTLP exporter endpoint |
| `SENTRY_DSN` | No | — | Sentry error tracking DSN |

### Notifications

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat ID |
| `EMAIL_SMTP_HOST` | No | — | SMTP server host |
| `EMAIL_SMTP_PORT` | No | `587` | SMTP server port |
| `EMAIL_FROM` | No | — | From address |

### Grafana

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GRAFANA_ADMIN_USER` | No | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | **Yes** | — | Grafana admin password |
| `GRAFANA_SECRET_KEY` | **Yes** | — | Grafana session secret: `openssl rand -hex 32` |

---

## Project Structure

```
forex-trading-system/
├── backend/                          # Python Backend (FastAPI)
│   ├── src/forex_trading/
│   │   ├── main.py                   # Application entry point
│   │   ├── config.py                 # Pydantic Settings
│   │   ├── core/                     # Domain entities, security, rate limiting
│   │   ├── api/                      # REST + WebSocket endpoints
│   │   │   ├── routers/              # Domain-specific route modules
│   │   │   │   ├── auth.py           # Login, register, MFA, password reset
│   │   │   │   ├── trading.py        # Orders, positions, deals
│   │   │   │   ├── risk.py           # Risk state, config, alerts, overrides
│   │   │   │   ├── market.py         # Market data, symbols
│   │   │   │   ├── strategy.py       # Strategy management
│   │   │   │   ├── broker.py         # Broker account management
│   │   │   │   ├── accounts.py       # User accounts and profiles
│   │   │   │   ├── analytics.py      # Trading analytics
│   │   │   │   ├── users.py          # User admin
│   │   │   │   └── ws.py             # WebSocket router registration
│   │   │   ├── schemas/              # Pydantic request/response models
│   │   │   ├── dependencies.py       # FastAPI dependency injection
│   │   │   └── websocket.py          # WebSocket connection manager
│   │   ├── ai/                       # AI Orchestration & Agents
│   │   │   ├── agents/               # 9 specialized agents
│   │   │   ├── consensus/            # Weighted voting engine
│   │   │   ├── xai/                  # Explainable AI (SHAP-based)
│   │   │   ├── services/             # AI service layer
│   │   │   └── orchestrator.py       # AI orchestrator
│   │   ├── strategy/                 # Strategy Engine
│   │   │   ├── strategies/           # 7 trading strategies
│   │   │   ├── registry/             # Strategy registry
│   │   │   └── engine.py             # Strategy selection & validation
│   │   ├── risk/                     # Risk Engine (Authoritative)
│   │   │   ├── services/             # Risk services
│   │   │   ├── middleware/           # Risk middleware
│   │   │   └── engine.py             # Circuit breaker, position sizing
│   │   ├── execution/                # Execution Engine
│   │   │   ├── engine.py             # Order placement & lifecycle
│   │   │   └── position_manager.py   # Trailing stops, partial close
│   │   ├── broker/                   # Broker Gateway Plugin System
│   │   │   ├── plugins/              # OANDA, MT4, MT5, Paper
│   │   │   ├── discovery/            # Broker auto-discovery
│   │   │   └── gateway.py            # Unified broker interface
│   │   ├── market_data/              # Market Data Service
│   │   ├── analytics/                # Analytics & Reporting
│   │   ├── notifications/            # Slack, Telegram, Email
│   │   ├── shared/                   # Shared Infrastructure
│   │   │   ├── database/             # SQLAlchemy models, UoW, repositories
│   │   │   ├── monitoring/           # Prometheus, logging, tracing
│   │   │   ├── messaging/            # Kafka / RabbitMQ producers/consumers
│   │   │   ├── cache/                # Redis caching
│   │   │   ├── security/             # Secrets, audit, API keys
│   │   │   └── di.py                 # Dependency injection container
│   │   └── ml/                       # ML model training artifacts
│   └── tests/                        # 300+ tests
│       ├── unit/                     # Unit tests (no external services)
│       ├── integration/              # Integration tests (mocked services)
│       ├── security/                 # Security & auth tests
│       ├── e2e/                      # End-to-end tests
│       ├── load/                     # Performance / load tests
│       ├── conftest.py               # Shared fixtures
│       └── factories.py              # Test data factories
├── frontend/                         # Next.js Dashboard
│   ├── src/
│   │   ├── app/                      # App Router pages
│   │   ├── components/               # React components
│   │   └── lib/                      # API client & utilities
│   └── public/
├── ml/                               # ML Models & Training Scripts
├── docker/                           # Docker configuration
│   ├── docker-compose.yml            # Full stack compose
│   ├── Dockerfile.backend            # Backend container
│   ├── Dockerfile.frontend           # Frontend container
│   └── nginx/                        # Nginx reverse proxy config
├── infrastructure/                   # Infrastructure as Code
│   ├── k8s/                          # Kubernetes manifests
│   │   ├── backend/                  # Backend deployment, HPA, PDB, secrets
│   │   ├── frontend/                 # Frontend deployment
│   │   ├── postgres/                 # PostgreSQL StatefulSet
│   │   ├── redis/                    # Redis StatefulSet
│   │   ├── kafka/                    # Kafka cluster
│   │   ├── monitoring/               # Prometheus, Grafana
│   │   └── ingress.yaml              # ALB ingress
│   ├── monitoring/                   # Prometheus config & Grafana dashboards
│   ├── db/                           # DB init scripts
│   └── *.tf                          # Terraform AWS IaC
├── scripts/                          # Operational scripts
│   ├── deploy.sh                     # Deployment pipeline
│   ├── rollback.sh                   # Rollback procedure
│   ├── backup-db.sh                  # PostgreSQL backup
│   └── seed-data.sh                  # Database seeding
├── docs/                             # Documentation
├── .env.example                      # Environment variable template
├── Makefile                          # Build, test, deploy, lint targets
├── CONTRIBUTING.md                   # Contribution guidelines
├── CHANGELOG.md                      # Release history
└── LICENSE                           # MIT license
```

---

## Key Features

### Multi-Broker Support
Unified interface across **OANDA**, **MetaTrader 4/5**, **FXCM**, **cTrader**, **Interactive Brokers**, and a built-in **Paper Trading** simulator. Plugin architecture makes adding new brokers a single-file implementation.

### AI-Powered Analysis
**9 specialized agents** (Market Structure, Trend, Liquidity, Volatility, Sentiment, Smart Money, Risk AI, Entry AI, Exit AI) with dynamic weighted consensus. All decisions are explained via SHAP-based XAI narratives.

### Smart Money Concepts (SMC)
Detects Order Blocks, Fair Value Gaps (FVGs), Liquidity Zones, Break of Structure (BOS), and Change of Character (CHoCH) — the institutional framework.

### Institutional Risk Management
**Authoritative Risk Engine** with circuit breaker, drawdown limits, position sizing (ATR/Kelly-based), correlation checks, and emergency liquidation. **No other component can override the Risk Engine.**

### Explainable AI (XAI)
Full audit trail for every trading decision: which agents voted which way, what confidence, what market data influenced them, and why the final decision was made.

### Real-Time Dashboard
Live P&L, open positions, AI signals, risk state, and performance metrics via WebSocket streaming.

### Backtesting Engine
Historical strategy validation with realistic fills, slippage modeling, and comprehensive performance reports.

---

## Development Workflow

```bash
# Activate virtual environment
cd backend
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with all extras
pip install -e ".[all]"

# Run tests
make test                    # All tests with coverage
make test-unit               # Unit tests only
make test-integration        # Integration tests only
make test-security           # Security tests
make test-e2e                # End-to-end tests

# Lint and format
make lint                    # ruff check + mypy
make format                  # ruff format
make lint-fix                # Auto-fix lint issues

# Database
make migrate                 # Run pending migrations
make migrate-new name="desc" # Create new migration
make seed                    # Seed database with sample data
make backup                  # Backup PostgreSQL database

# Docker
make build                   # Build Docker images
make up                      # Start all services
make down                    # Stop all services
```

---

## API Documentation Overview

Once running, access the interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Domain Endpoints

| Domain | Prefix | Description |
|--------|--------|-------------|
| Auth | `/api/v1/auth` | Register, login, refresh, MFA, password reset |
| Trading | `/api/v1/trading` | Orders, positions, deals, order modifications |
| Market Data | `/api/v1/market` | Symbols, quotes, candles, market structure |
| Risk | `/api/v1/risk` | Risk state, config, alerts, circuit breaker overrides |
| Strategy | `/api/v1/strategy` | Strategy selection, parameters, performance |
| Broker | `/api/v1/broker` | Account connections, credentials, status |
| Accounts | `/api/v1/accounts` | User profiles, broker accounts |
| Analytics | `/api/v1/analytics` | Performance reports, win rates, attribution |
| Users | `/api/v1/users` | User management (admin) |
| WebSocket | `/ws/*` | Real-time streaming endpoints |

### WebSocket Channels

| Channel | Path | Description |
|---------|------|-------------|
| Ticks | `/ws/market/{symbol}` | Real-time bid/ask prices |
| Orders | `/ws/orders/{account_id}` | Order status updates |
| Positions | `/ws/positions/{account_id}` | Position updates |
| Signals | `/ws/signals` | AI trade signals |
| Alerts | `/ws/alerts` | Risk alerts |
| Dashboard | `/ws/dashboard` | All channels combined |

See [docs/API.md](docs/API.md) for the complete API reference.

---

## Security Considerations

- **JWT with RS256** (asymmetric) in production — access tokens expire in 15 minutes
- **Refresh token rotation** — each refresh invalidates the previous token
- **MFA via TOTP** with 8 backup codes for sensitive operations
- **API keys** prefixed (`fx_key_`) with SHA-256 hashing; keys shown once at creation
- **Rate limiting** via Redis sliding window — 100 req/min per IP, 10/min for login
- **Audit logging** — every sensitive operation is immutably logged
- **Secrets management** — no secrets in code; AWS Secrets Manager in production
- **CSP, HSTS, Permissions-Policy** security headers on every response
- **Network isolation** — 3-tier Docker networks (DMZ, app, db) with internal-only access

See [docs/SECURITY.md](docs/SECURITY.md) for the complete security guide.

---

## Monitoring & Alerting Guide

### Metrics (Prometheus)
The backend exposes 28+ Prometheus metrics at `/metrics` covering:

- **HTTP**: request count, duration histogram, in-flight requests
- **WebSocket**: active connections, message throughput
- **Trading**: executions, fill rates, volume, P&L
- **AI**: signal count, agent latency, confidence scores, drift alerts
- **Risk**: assessments, vetoes, circuit breaker state, alerts
- **System**: process metrics, cache hit rates

### Dashboards (Grafana)
Pre-built dashboards in `infrastructure/monitoring/grafana/dashboards/`:

- `forex_overview.json` — P&L, positions, win rate
- `ai_agents.json` — Agent consensus, signal history
- `risk_engine.json` — Drawdown, circuit breaker status
- `system_health.json` — API latency, error rates, resource usage

### Alerting
Prometheus alert rules in `infrastructure/monitoring/alerts.yaml` trigger on:
- API error rate > 1%
- P95 latency > 500ms
- Circuit breaker activated
- Database connection pool > 90%
- No AI signals for 15 minutes
- Trade execution failures > 5%
- Redis / PostgreSQL down

### Distributed Tracing (OpenTelemetry + Jaeger)
Every request is traced across service boundaries. View traces in the Jaeger UI.

---

## Deployment Guide

### Docker
```bash
make build    # Build images
make up       # Start services
make down     # Stop services
```

### Kubernetes
```bash
kubectl apply -f infrastructure/k8s/namespace.yaml
kubectl apply -f infrastructure/k8s/postgres/
kubectl apply -f infrastructure/k8s/redis/
kubectl apply -f infrastructure/k8s/kafka/
kubectl apply -f infrastructure/k8s/backend/
kubectl apply -f infrastructure/k8s/frontend/
kubectl apply -f infrastructure/k8s/monitoring/
kubectl apply -f infrastructure/k8s/ingress.yaml
```

### CI/CD Pipeline
```
git push → GitHub Actions →
  1. pytest (unit + integration + security)
  2. ruff lint + mypy type check
  3. docker build + push to ECR
  4. kubectl apply (rolling update, maxUnavailable=0)
  5. smoke test against staging
  6. promote to production
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the complete deployment guide.

---

## Troubleshooting FAQ

### "Database connection refused"
Ensure PostgreSQL is running. Check `DATABASE_URL` and `POSTGRES_PASSWORD` in `.env`. For Docker: `docker compose logs postgres`.

### "Redis connection error"
Ensure Redis is running. Verify `REDIS_URL` and `REDIS_PASSWORD`. Redis binds to localhost only in Docker — ensure your app connects from within the same network.

### "Kafka broker not available"
Wait for Kafka to finish its KRaft initialization (can take 30-60s on first start). Check `docker compose logs kafka`. Verify `KAFKA_BOOTSTRAP_SERVERS`.

### "JWT token invalid / expired"
Access tokens expire in 15 minutes. Use `/auth/refresh` to obtain a new pair. If using RS256, ensure the private key hasn't changed.

### "No AI signals being generated"
Check `AI_MIN_AGENTS` and `AI_MIN_AGREEMENT_THRESHOLD`. Ensure market data is flowing. Verify agents are registered. Check logs for agent errors.

### "Circuit breaker keeps tripping"
Review `MAX_DRAWDOWN_TOTAL_PCT` and `MAX_DRAWDOWN_DAILY_PCT` settings. The circuit breaker has a 60-minute cooldown by default. Admin can reset via `POST /api/v1/risk/circuit-breaker/reset`.

### "Rate limit exceeded"
Default is 100 requests per minute per IP. Login is limited to 10 per minute. Wait for the window to reset or increase limits in configuration.

### "Orders not executing"
Check broker connection status (`GET /api/v1/broker/accounts`). Verify API keys. For paper trading, ensure PaperTradingPlugin is selected. Check risk engine logs for veto reasons.

### "Alembic migration fails"
Ensure the database exists and is accessible. Run `alembic upgrade head` from the `backend/` directory. If a migration is stuck, check `alembic_version` table.

---

## Project Status

**Version**: 0.1.0 (Beta)

Completed phases:
- ✅ Core Infrastructure (DI, UoW, repositories, Kafka, risk engine, position manager)
- ✅ AI/ML Layer (orchestrator, 9 agents, consensus, XAI, drift detection)
- ✅ Monitoring & Observability (structlog, Prometheus, OpenTelemetry, health checks)
- ✅ Security Hardening (secrets management, rate limiting, JWT, audit logging, API keys)
- ✅ Testing Infrastructure (300+ tests across all layers)
- ✅ Deployment & CI/CD (Docker, K8s, CI/CD pipelines, Terraform)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
