# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-14

### Added

#### Core Infrastructure
- Complete dependency injection container with `Container` class managing all service lifetimes
- Unit of Work (UoW) pattern with `UnitOfWorkFactory` for transactional consistency
- Repository pattern with typed CRUD repositories for all domain entities
- Kafka message bus integration with KRaft mode (no Zookeeper dependency)
- RabbitMQ support as alternative message bus for development
- Event-driven architecture with typed event schemas (CloudEvents compatible)
- SQLAlchemy 2.0 async ORM with full model layer (User, Order, Position, Deal, AIDecision, etc.)
- Alembic migration framework with initial schema

#### Risk Engine (Authoritative)
- `RiskEngine` — absolute override authority over all trading decisions
- Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN)
- Pre-trade checks: position size, exposure, drawdown, correlation, spread
- Real-time position monitoring with P&L tracking
- Dynamic stop-loss management (ATR-trailing)
- Emergency position liquidation capability
- Persisted risk state (survives process restart)
- `RiskLimits` configuration with per-account overrides
- Risk alert generation with severity levels (INFO, WARNING, CRITICAL)
- Risk override logging and audit trail

#### Position Manager
- In-memory position tracking with thread-safe operations
- Trailing stop logic: breakeven at 1×ATR, partial close at 2×ATR, trail at 3×ATR
- Max holding time enforcement with force close
- Symbol-level position limits and correlation checks
- Unrealized P&L calculation

#### Execution Engine
- Order lifecycle management (new → filled → cancelled → rejected)
- Broker-agnostic order placement through plugin system
- Order modification (stop loss, take profit updates)
- Position close operations
- Deal recording and reconciliation
- Support for market, limit, stop, and OCO orders

#### Strategy Engine
- Strategy registry with 7 trading strategies:
  - `TrendFollowing` — EMA alignment with ADX filter
  - `Pullback` — EMA20 retracement entries
  - `Breakout` — Volume-confirmed structure breaks
  - `MeanReversion` — Bollinger Band extremes with RSI confirmation
  - `Scalping` — Micro-structure with low spread requirement
  - `LondonOpen` — Asian range break at London open
  - `AsianRange` — Range-bound during Asian session
- Regime-based strategy selection (Trending Up/Down, Ranging, Volatile, Low Volatility)
- Strategy-specific parameter sets per symbol
- Performance tracking with win rate, profit factor, and Sharpe ratio

#### AI/ML Layer
- `AIOrchestrator` — coordinates 9 specialized AI agents
- Agent system with `BaseAgent` abstract interface:
  - `MarketStructureAgent` — ICT/SMC swing analysis, BOS, CHoCH detection
  - `TrendAgent` — multi-timeframe EMA, ADX, MACD
  - `LiquidityAgent` — order blocks, FVGs, liquidity sweeps
  - `VolatilityAgent` — ATR, Bollinger Bands, VWAP
  - `SentimentAgent` — RSI, CoT, momentum divergences
  - `SmartMoneyAgent` — discount/premium zones, equilibrium
  - `RiskAgent` — spread, drawdown, news veto (independent circuit breaker)
  - `EntryAgent` — micro-structure entry timing, R:R optimization
  - `ExitAgent` — trailing stop, TP, reversal detection, session-end
- Dynamic weighted consensus engine:
  - Regime-dependent agent weights
  - Performance-based weight adjustment (70% base / 30% performance)
  - Adaptive drift detection with 20-signal window
  - Minimum agreement threshold of 0.60 (configurable)
- `TradeExplainer` — SHAP-style narrative generation for every decision
- Full persistence of every AIDecision with agent-level signals
- `AgentPerformance` tracking with continuous weight updates

#### API Layer
- FastAPI application with lifespan-managed DI container
- RESTful endpoints organized by domain modules
- WebSocket pub/sub `ConnectionManager` with 6 channels
- Pydantic v2 request/response schemas with strict validation
- Health check endpoints (`/health`, `/health/live`, `/health/ready`, `/health/detailed`)
- System info endpoint
- Prometheus metrics endpoint at `/metrics`

#### Authentication & Authorization
- JWT authentication with RS256 (production) / HS256 (development)
- Audience-based token type binding (access vs. refresh tokens)
- 5-minute access token expiry (hardened default)
- 24-hour refresh token expiry with single-use rotation
- Token revocation via Redis blacklist (in-memory fallback)
- `SecurityManager` with password hashing (bcrypt) and permission checks
- Role-Based Access Control (RBAC) with 4 roles: `viewer`, `trader`, `admin`, `superadmin`
- MFA via TOTP (pyotp) with 8 backup codes
- API key authentication with `fx_key_` prefix and SHA-256 hashing
- Fernet-based credential encryption for broker secrets

#### Security Hardening
- Secrets management with `SecretsSettings` — production fail-fast validation
- Rate limiting with Redis sliding window (per-IP, per-user, per-API-key)
- Default rules: 100 req/min general, 10/min login, 60/min trading endpoints
- 429 Too Many Requests with Retry-After header
- CORS middleware with configurable whitelist
- TrustedHost middleware in production
- Security headers: CSP, HSTS (preload), Permissions-Policy, Referrer-Policy, X-Content-Type-Options
- Request size limiting (1 MB default, 512 KB for JSON)
- Audit logging middleware — 50+ sensitive actions tracked in immutable `audit_logs` table
- SQL injection protection via SQLAlchemy ORM parameterized queries

#### Monitoring & Observability
- **28 Prometheus metrics** across all subsystems:
  - HTTP: `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_flight`
  - WebSocket: `websocket_connections_active`, `websocket_messages_total`
  - Trading: `trade_executions_total`, `trade_execution_duration_seconds`, `trade_fills_total`, `trade_volume_lots`
  - Positions: `open_positions_count`, `portfolio_pnl_usd`
  - Risk: `risk_assessments_total`, `risk_vetoes_total`, `risk_alerts_total`, `circuit_breaker_state`
  - AI: `ai_signals_generated_total`, `ai_signal_confidence`, `ai_agent_latency_seconds`, `ai_drift_alerts_total`
  - System: `cache_hits_total`, `cache_misses_total`, `cache_operations_duration_seconds`
- Structured logging via `structlog` with JSON output format
- OpenTelemetry distributed tracing with Jaeger exporter
- FastAPI middleware instrumentation
- SQLAlchemy query tracing
- HTTPX client tracing

#### Deployment & CI/CD
- Multi-stage Dockerfile for backend (FastAPI) with pip cache optimization
- Multi-stage Dockerfile for frontend (Next.js) with standalone output
- Production Docker Compose with 10 services:
  - PostgreSQL 16 + TimescaleDB
  - Redis 7 with AOF persistence
  - Kafka in KRaft mode
  - FastAPI backend (2 replicas)
  - Next.js frontend
  - Nginx reverse proxy with SSL
  - Prometheus + Grafana
  - Flower (Celery monitor)
- 3-tier network isolation: `db_network` (internal), `backend_network` (internal), `frontend_network` (DMZ)
- Kubernetes manifests:
  - Backend: Deployment (3 replicas), Service, HPA (2-10), PDB, ConfigMap, Secrets
  - Frontend: Deployment, Service
  - PostgreSQL: StatefulSet with persistent volumes
  - Redis: StatefulSet
  - Kafka: StatefulSet (3 brokers)
  - Monitoring: Prometheus, Grafana deployments
  - Ingress: ALB ingress with path-based routing
- GitHub Actions CI/CD pipeline:
  - `ci.yml` — test, lint, build on PR
  - `cd.yml` — deploy to staging/production
- Terraform IaC:
  - VPC with public/private subnets
  - EKS cluster with node groups
  - RDS PostgreSQL (Multi-AZ)
  - ElastiCache Redis
  - MSK Kafka
  - ECR repositories
  - IAM roles with least privilege
  - Security groups and NACLs
  - Secrets Manager integration
- Makefile with 25+ targets for build, test, lint, deploy, backup

#### Testing Infrastructure (300+ tests)
- Unit tests for all domain entities, value objects, and business logic
- Integration tests for database repositories, API endpoints, and service layer
- Security tests for authentication, authorization, rate limiting, and input validation
- End-to-end tests for complete trade lifecycle (mocked broker)
- Load/performance tests for critical paths
- Property-based testing with Hypothesis
- Test factories for all domain models
- Comprehensive fixtures in `conftest.py`
- Pytest configuration with markers: `unit`, `integration`, `security`, `slow`, `e2e`, `load`
- Coverage reporting with 80% threshold

### Security

- JWT access token expiry reduced from 15 to 5 minutes
- JWT refresh token expiry reduced from 7 days to 24 hours
- Audience-based token type binding prevents token reuse across contexts
- Production secret validation with fail-fast startup
- Rate limiting on all endpoints with per-authentication-type granularity
- Fernet encryption for stored broker credentials
- API keys hashed with SHA-256 (never stored in plaintext)
- Security headers enforced on every response
- Read-only root filesystem for Docker containers
- `no-new-privileges` security option on all containers
- Internal network isolation with no external access for database tier

[0.1.0]: https://github.com/your-org/forex-trading-system/releases/tag/v0.1.0
