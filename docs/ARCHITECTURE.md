# Architecture — Institutional Forex AI Trading Platform

> **Documentation for version 0.1.0**  
> Last updated: 2026-07-14

---

## Table of Contents

1. [System Context Diagram](#1-system-context-diagram)
2. [Container Diagram](#2-container-diagram)
3. [Component Diagram](#3-component-diagram)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Deployment Architecture](#5-deployment-architecture)
6. [Design Decisions and Trade-offs](#6-design-decisions-and-trade-offs)

---

## 1. System Context Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              TRADERS & ADMINISTRATORS                             │
│                    (Dashboard, API Clients, Mobile, Telegram)                      │
└────────────────────────────────┬─────────────────────────────────────────────────┘
                                 │  HTTPS / WSS
                                 │
┌────────────────────────────────▼─────────────────────────────────────────────────┐
│                             FOREX AI TRADING SYSTEM                                │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │  "An institutional-grade autonomous AI trading platform that executes       │  │
│  │   forex trades based on multi-agent AI analysis, institutional risk         │  │
│  │   management, and configurable strategies."                                 │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  REST API    │  │  WebSocket   │  │  Dashboard   │  │   Scheduled Tasks    │ │
│  │  (FastAPI)   │  │  Streaming   │  │  (Next.js)   │  │   (Analytics, etc.) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└──────────┬───────────────────────────────────────────────────────────────────────┘
           │
           │  HTTPS / REST / WS
           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             EXTERNAL SYSTEMS                                       │
│                                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  OANDA       │  │  MetaTrader  │  │  FXCM / IB   │  │  Market Data Feeds   │ │
│  │  (REST API)  │  │  4/5 (TCP)   │  │  (WebSocket) │  │  (News, Calendar)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### External Systems

| System | Protocol | Purpose |
|--------|----------|---------|
| **OANDA** | REST + Streaming (v20) | Primary broker for development and live trading |
| **MetaTrader 4** | TCP Socket (EA Bridge) | Legacy broker connectivity |
| **MetaTrader 5** | Native Python library | Modern MetaQuotes platform |
| **FXCM** | REST + WebSocket | Alternative broker |
| **Interactive Brokers** | TWS API | Multi-asset brokerage |
| **Market Data Vendors** | Various | News feeds, economic calendar |

---

## 2. Container Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           CONTAINERS & SERVICES                                    │
│                                                                                   │
│  ┌────────────────────┐    ┌────────────────────┐    ┌────────────────────────┐  │
│  │    API Gateway     │    │  WebSocket Server  │    │     Frontend (Next.js) │  │
│  │  (FastAPI + Auth)  │    │  (ConnectionManager)│    │   (SSR + Dashboard)   │  │
│  └────────┬───────────┘    └────────┬───────────┘    └───────────┬────────────┘  │
│           │                         │                            │               │
│  ┌────────┴─────────────────────────┴────────────────────────────┴────────────┐ │
│  │                         MESSAGE BUS (KAFKA)                                  │ │
│  │   Topics: market.ticks, market.candles, trading.orders, trading.positions,  │ │
│  │           risk.alerts, ai.signals, analytics.trades, system.events          │ │
│  └────────┬──────────┬──────────┬──────────┬──────────┬──────────┬────────────┘ │
│           │          │          │          │          │          │              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │
│  │ Market │ │   AI   │ │Strategy│ │  Risk  │ │Execution│ │ Broker │             │
│  │  Data  │ │Orch.   │ │ Engine │ │ Engine │ │ Engine  │ │Gateway │             │
│  │Service │ │Service │ │Service │ │Service │ │Service  │ │Service │             │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘             │
│      │          │          │          │          │          │                   │
│  ┌───┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────────┐   │
│  │                         DATA STORES                                       │   │
│  │                                                                           │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │   │
│  │  │PostgreSQL │  │TimescaleDB│  │   Redis   │  │    S3     │              │   │
│  │  │  (OLTP)   │  │(Time-Ser.)│  │(Cache/Pub)│  │(Objects)  │              │   │
│  │  │ Users     │  │ Ticks     │  │ Prices     │  │ Models    │              │   │
│  │  │ Orders    │  │ Candles   │  │ Sessions   │  │ Reports   │              │   │
│  │  │ Positions │  │ Volatility│  │ Rate Lim.  │  │ Backtests │              │   │
│  │  │ Risk State│  │           │  │ Pub/Sub    │  │ Archives  │              │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Data Store Details

| Store | Technology | Purpose | Data |
|-------|-----------|---------|------|
| **PostgreSQL** | PostgreSQL 16 + asyncpg | OLTP, relational state | Users, orders, positions, risk config, audit logs, AI decisions |
| **TimescaleDB** | TimescaleDB (pg extension) | Time-series optimization | Ticks (hypertable), OHLCV candles, volatility metrics |
| **Redis** | Redis 7 | Cache, Pub/Sub, rate limiting | Current prices, session state, rate limit counters, real-time pub/sub |
| **S3** | AWS S3 / MinIO | Object storage | Trained ML models, backtest reports, historical archives |

### Kafka Topics

| Topic | Producer | Consumer(s) | Schema |
|-------|----------|-------------|--------|
| `market.ticks` | Broker plugins | Market Data Service, AI Agents | `{symbol, bid, ask, volume, timestamp}` |
| `market.candles` | Market Data Service | AI Agents, Strategy Engine | `{symbol, timeframe, open, high, low, close, volume}` |
| `trading.orders` | Execution Engine | Position Manager, Risk Engine | `{order_id, symbol, side, qty, price, status}` |
| `trading.positions` | Position Manager | Risk Engine, Analytics | `{position_id, symbol, side, size, pnl, sl, tp}` |
| `risk.alerts` | Risk Engine | Notification Service, Dashboard | `{level, category, message, details}` |
| `ai.signals` | AI Orchestrator | Strategy Engine, Dashboard | `{symbol, direction, confidence, agents, rationale}` |
| `analytics.trades` | Execution Engine | Analytics Service | `{trade_id, pnl, roi, duration, strategy}` |
| `system.events` | All services | Monitoring, Audit | `{type, source, severity, data}` |

---

## 3. Component Diagram

### 3.1 Core Domain Modules

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CORE DOMAIN MODULES                                     │
│                                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐      │
│  │                         AI ORCHESTRATOR                                  │      │
│  │  ┌────────────────────────────────────────────────────────────────┐     │      │
│  │  │                         Agent Manager                          │     │      │
│  │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │     │      │
│  │  │  │Market  │ │  Trend │ │Liquid. │ │Volatility│ │Sentiment│      │     │      │
│  │  │  │Struct. │ │  Agent │ │ Agent  │ │  Agent  │ │  Agent  │      │     │      │
│  │  │  │ Agent  │ │        │ │        │ │         │ │         │      │     │      │
│  │  │  └────────┘ └────────┘ └────────┘ └─────────┘ └─────────┘      │     │      │
│  │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                  │     │      │
│  │  │  │Smart   │ │  Risk  │ │  Entry │ │  Exit  │                  │     │      │
│  │  │  │Money   │ │  Agent │ │  Agent │ │  Agent │                  │     │      │
│  │  │  │ Agent  │ │        │ │        │ │        │                  │     │      │
│  │  │  └────────┘ └────────┘ └────────┘ └────────┘                  │     │      │
│  │  └────────────────────────────────────────────────────────────────┘     │      │
│  │                                                                           │      │
│  │  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────┐   │      │
│  │  │   Consensus Engine   │  │   Trade Explainer    │  │Drift Detector│   │      │
│  │  │  (Weighted Voting)   │  │  (XAI Narrative)     │  │ (20-win win) │   │      │
│  │  └──────────────────────┘  └──────────────────────┘  └──────────────┘   │      │
│  └────────────────────────────────────────────────────────────────────────┘      │
│                                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  ┌────────────┐   │
│  │  STRATEGY      │  │  RISK ENGINE   │  │ EXECUTION ENGINE │  │  BROKER    │   │
│  │  ENGINE        │  │ (Authoritative)│  │                  │  │  GATEWAY   │   │
│  │                │  │                │  │                  │  │            │   │
│  │ • Registry (7) │  │ • Circuit      │  │ • Order Manager  │  │ • OANDA    │   │
│  │ • Regime-based │  │   Breaker      │  │ • Position       │  │ • MT4/5    │   │
│  │   selection    │  │ • Pre-trade    │  │   Manager        │  │ • FXCM     │   │
│  │ • Strategy     │  │   checks       │  │ • Deal Recording │  │ • IB       │   │
│  │   validation   │  │ • Real-time    │  │ • Trailing Stops │  │ • Paper    │   │
│  │ • Performance  │  │   monitoring   │  │ • OCO Orders     │  │            │   │
│  │   tracking     │  │ • Override API │  │ • Slippage       │  │            │   │
│  └────────────────┘  └────────────────┘  └──────────────────┘  └────────────┘   │
│                                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐                    │
│  │  MARKET DATA   │  │  NOTIFICATIONS │  │  SHARED INFRA    │                    │
│  │                │  │                │  │                  │                    │
│  │ • Tick ingest  │  │ • Slack        │  │ • DI Container   │                    │
│  │ • Candle aggr. │  │ • Telegram     │  │ • UoW / Repos    │                    │
│  │ • Session det. │  │ • Email        │  │ • Kafka Producers │                    │
│  │ • SMC analysis │  │ • WebSocket    │  │ • Redis Cache    │                    │
│  └────────────────┘  └────────────────┘  │ • Monitoring     │                    │
│                                           │ • Security       │                    │
│                                           └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Shared Infrastructure (Cross-Cutting)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          SHARED INFRASTRUCTURE MODULES                            │
│                                                                                   │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐  │
│  │  DI Container       │  │  Database Layer      │  │  Security               │  │
│  │                     │  │                     │  │                         │  │
│  │ • Service registry  │  │ • SQLAlchemy async   │  │ • JWT (RS256/HS256)    │  │
│  │ • Lifetime mgmt     │  │ • Unit of Work       │  │ • bcrypt password hash │  │
│  │ • Lazy initialization│  │ • Repository pattern │  │ • MFA (TOTP)           │  │
│  │ • Event publishing  │  │ • Alembic migrations │  │ • API keys (SHA-256)   │  │
│  │                     │  │ • Connection pooling  │  │ • Fernet encryption    │  │
│  └─────────────────────┘  └─────────────────────┘  │ • Rate limiting (Redis) │  │
│                                                     │ • Audit logging         │  │
│  ┌─────────────────────┐  ┌─────────────────────┐  └─────────────────────────┘  │
│  │  Monitoring         │  │  Messaging           │                               │
│  │                     │  │                     │                               │
│  │ • structlog logging │  │ • Kafka producer     │                               │
│  │ • 28 Prometheus     │  │ • Kafka consumer     │                               │
│  │   metrics           │  │ • RabbitMQ (alt)     │                               │
│  │ • OpenTelemetry     │  │ • Event serialization│                               │
│  │   tracing           │  │ • CloudEvents schema │                               │
│  │ • Jaeger exporter   │  │                     │                               │
│  └─────────────────────┘  └─────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow Diagrams

### 4.1 Trade Lifecycle (End-to-End)

```
                                      TRADE LIFECYCLE
                                      ═══════════════

  MARKET DATA               AI ANALYSIS              RISK CHECK
  ────────────              ───────────              ──────────

  Broker Plugin ──ticks──►  AIOrchestrator ──req──►  RiskEngine
       │                       │                        │
       │                  ┌────┴────┐              ┌────┴────┐
       │                  │ 9 Agents│              │ Pre-    │
       │                  │ (parallel)             │ trade   │
       │                  └────┬────┘              │ checks  │
       │                       │                   │ (7 gates)│
       │                  ┌────┴────┐              └────┬────┘
       │                  │Consensus │                   │
       │                  │ Engine   │              ┌────┴────┐
       │                  └────┬────┘              │Approved │
       │                       │                   │or       │
       │                  ┌────┴────┐              │Rejected │
       │                  │XAI      │              └────┬────┘
       │                  │Explainer│                   │
       │                  └────┬────┘                   │
       │                       │                        │
       │                       ▼                        │
       │               OrchestratorResult               │
       │             (signal + explanation)              │
       │                       │                        │
       │                       ▼                        │
       │               STRATEGY ENGINE                  │
       │               ┌──────────────┐                 │
       │               │ Select best  │                 │
       │               │ strategy for │                 │
       │               │ regime       │                 │
       │               └──────┬───────┘                 │
       │                      │                         │
       │                      ▼                         │
       │               PositionSizer                    │
       │          (ATR/Kelly position calc)              │
       │                      │                         │
       │                      ▼                         │
       │               ┌──────────────────┐             │
       └──────────────►│  RiskEngine      │◄────────────┘
                       │  assess_trade()  │
                       └────────┬─────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
               REJECTED                 APPROVED
                    │                       │
                    ▼                       ▼
               ┌──────────┐          ┌──────────────┐
               │ Log &    │          │ Execution    │
               │ Alert    │          │ Engine       │
               └──────────┘          │ process_     │
                                     │ signal()     │
                                     └──────┬───────┘
                                            │
                                     ┌──────┴───────┐
                                     │ BrokerGateway│
                                     │ place_order()│
                                     └──────┬───────┘
                                            │
                                     ┌──────┴───────┐
                                     │ Position     │
                                     │ Manager      │
                                     │ (monitoring) │
                                     └──────┬───────┘
                                            │
                                     ┌──────┴───────┐
                                     │ Trade Close  │
                                     │ (SL/TP/manual)│
                                     └──────┬───────┘
                                            │
                                     ┌──────┴───────┐
                                     │ Analytics    │
                                     │ (PnL, stats) │
                                     └──────────────┘
```

### 4.2 Tick Processing Flow

```
Broker Plugin
     │
     │ (bid/ask)
     ▼
Kafka Topic: market.ticks
     │
     ├──► Market Data Service
     │     ├── Store in TimescaleDB hypertable
     │     ├── Aggregate into OHLCV candles
     │     │     └──► Kafka: market.candles
     │     ├── Detect market regime (session, volatility)
     │     └──► Redis cache (latest price)
     │
     ├──► AI Agents (subscribed consumers)
     │     └── Update technical indicators
     │
     ├──► Position Manager
     │     └── Update unrealized P&L, check trailing stops
     │
     └──► Dashboard (via WebSocket broadcast)
           └── Update real-time charts
```

### 4.3 AI Signal Flow

```
MarketContext (candles, regime, metadata)
     │
     ▼
AI Orchestrator
     │
     ├──► Agent 1 (Market Structure)
     ├──► Agent 2 (Trend)
     ├──► Agent 3 (Liquidity)
     ├──► Agent 4 (Volatility)
     ├──► Agent 5 (Sentiment)
     ├──► Agent 6 (Smart Money)
     ├──► Agent 7 (Risk AI)
     ├──► Agent 8 (Entry AI)
     └──► Agent 9 (Exit AI)
          │
          ▼ (all agents run concurrently)
     AgentSignal[]
          │
          ▼
     ConsensusEngine
          │
          ├── Compute weighted agreement
          ├── Check agreement ≥ 0.60 threshold
          ├── Check conflict ≤ 0.30 threshold
          └──► ConsensusResult (direction, confidence, agreement)
               │
               ▼
          TradeExplainer
               │
               ├── Generate SHAP-style narrative
               ├── Attribute contribution per agent
               └──► TradeExplanation (rationale, key factors)
                    │
                    ▼
               OrchestratorResult
                    │
                    ├── Persist to AIDecision table
                    ├── Publish to Kafka: ai.signals
                    └── Return to caller
```

### 4.4 Order Execution Flow

```
TradeSignal (approved by Risk Engine)
     │
     ▼
ExecutionEngine.process_signal()
     │
     ├── 1. Construct Order (symbol, side, qty, type)
     ├── 2. Pre-submission validation
     │      ├── Check news blackout window
     │      ├── Check spread ≤ max_spread_pips
     │      ├── Check correlated position limits
     │      └── Check daily trade count
     │
     ├── 3. BrokerGateway.place_order()
     │      └──► Broker-specific API call
     │
     ├── 4. Process fill response
     │      ├── Full fill → Create Position
     │      ├── Partial fill → Create Position (partial qty)
     │      └── Rejected → Log, alert, retry?
     │
     ├── 5. Position tracking
     │      ├── Add to in-memory store
     │      ├── Subscribe to price updates
     │      └── Begin trailing stop loop
     │
     └── 6. Analytics update
            └── Record trade attempt (success/failure)
```

### 4.5 Risk Engine Decision Flow

```
Trade Assessment Request
     │
     ▼
RiskEngine.assess_trade()
     │
     ├── 1. Circuit Breaker Check
     │      ├── If OPEN → REJECT (circuit breaker active)
     │      └── If HALF_OPEN → Allow 1 trade, then back to OPEN
     │
     ├── 2. Drawdown Check
     │      ├── If daily_drawdown ≥ daily_limit → REJECT
     │      ├── If total_drawdown ≥ max_limit → REJECT
     │      └── Otherwise → Continue
     │
     ├── 3. Position Size Check
     │      ├── Compute max_size = equity × max_position_size_pct%
     │      ├── If requested > max_size → REJECT (or adjust down)
     │      └── Otherwise → Continue
     │
     ├── 4. Total Exposure Check
     │      ├── current_exposure + new_exposure > max_total_exposure% → REJECT
     │      └── Otherwise → Continue
     │
     ├── 5. Symbol/Position Limits
     │      ├── Open positions for symbol ≥ max_per_symbol → REJECT
     │      ├── Total open positions ≥ max_positions → REJECT
     │      └── Otherwise → Continue
     │
     ├── 6. Correlation Check
     │      ├── Correlated exposure > max_correlated_exposure% → REJECT
     │      └── Otherwise → Continue
     │
     ├── 7. Consecutive Losses Check
     │      ├── consecutive_losses ≥ max_consecutive_losses → REJECT (cooling off)
     │      └── Otherwise → Continue
     │
     └── 8. APPROVED
            ├── Calculate risk_score
            ├── Log assessment
            ├── Update risk state
            └── Return RiskAssessment(is_approved=true)
```

---

## 5. Deployment Architecture

### 5.1 AWS Infrastructure (EKS)

```
                         AWS Route53 (DNS)
                              │
                     AWS CloudFront (CDN)
                              │
                     AWS WAF (Web Application Firewall)
                              │
                     AWS ALB (Application Load Balancer)
                      ├── /api/v1/*  →  Backend Service
                      ├── /ws/*      →  WebSocket Service
                      └── /*         →  Frontend Service

┌──────────────────────────────────────────────────────────────────────────────┐
│                         VPC (10.0.0.0/16)                                       │
│                                                                                │
│  ┌──────────────────── PUBLIC SUBNETS ─────────────────────────────────────┐  │
│  │  • Public ALB (internet-facing)                                         │  │
│  │  • NAT Gateway (for private subnet egress)                              │  │
│  │  • Bastion Host (SSH access, locked down)                               │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────── PRIVATE SUBNETS (Application) ──────────────────────┐  │
│  │  EKS Cluster — Namespace: forex-trading                                  │  │
│  │                                                                          │  │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │  │  Deployment: backend-api (3 replicas, HPA 2-10)                  │ │  │
│  │  │  Deployment: backend-worker (2 replicas, background tasks)       │ │  │
│  │  │  Deployment: ai-service (2 replicas, GPU optional)               │ │  │
│  │  │  Deployment: frontend (2 replicas)                               │ │  │
│  │  │  StatefulSet: postgresql (1 primary + 2 replicas, Multi-AZ)      │ │  │
│  │  │  StatefulSet: redis-cluster (6 nodes, 3 masters + 3 replicas)    │ │  │
│  │  │  StatefulSet: kafka (3 brokers, KRaft mode)                      │ │  │
│  │  │  Deployment: prometheus (1 replica, 30d retention)               │ │  │
│  │  │  Deployment: grafana (1 replica, persistent storage)             │ │  │
│  │  │  CronJob: analytics-aggregator (every 1h)                        │ │  │
│  │  │  CronJob: model-retraining (daily at 02:00 UTC)                  │ │  │
│  │  └────────────────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────── PRIVATE SUBNETS (Data) ────────────────────────────┐  │
│  │  • RDS PostgreSQL (Multi-AZ, automated backups, 35-day retention)      │  │
│  │  • ElastiCache Redis (Cluster mode, auto-failover)                     │  │
│  │  • MSK Kafka (3 brokers, auto-rebalance)                                │  │
│  │  • S3 Buckets: models, backtest-results, logs, reports                 │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└──────────────────────────────────────────────────────────────────────────────┘

AWS Services:
  • RDS PostgreSQL (TimescaleDB extension) — managed primary with read replicas
  • ElastiCache Redis — managed cluster with auto-failover
  • MSK (Managed Streaming for Kafka) — fully managed Kafka
  • ECR — container image registry
  • S3 — ML model artifacts, backtest results, logs
  • Secrets Manager — JWT keys, broker credentials, API keys
  • CloudWatch — log aggregation and metric alarms
  • IAM — least-privilege service roles (IRSA)
```

### 5.2 Docker Compose (Local Development)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOCKER COMPOSE NETWORKS                              │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │  FRONTEND NETWORK (172.21.0.0/24) — DMZ Tier                     │       │
│  │                                                                   │       │
│  │  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐ │       │
│  │  │   Nginx      │────▶│   Frontend   │     │   (Internet)     │ │       │
│  │  │  :80/443     │     │  :3000       │     │   ← Traffic     │ │       │
│  │  └──────┬───────┘     └──────────────┘     └──────────────────┘ │       │
│  └─────────┼────────────────────────────────────────────────────────┘       │
│            │  (dual-homed)                                                     │
│  ┌─────────┼──────────────────────────────────────────────────────────┐       │
│  │  BACKEND NETWORK (172.20.0.0/24) — App Tier                        │       │
│  │         │                                                           │       │
│  │  ┌──────▼───────┐     ┌──────────────┐     ┌──────────────────┐   │       │
│  │  │   Backend    │     │   Kafka      │     │   Prometheus     │   │       │
│  │  │  :8000 (×2)  │     │  :9092       │     │   :9090          │   │       │
│  │  └──────┬───────┘     └──────────────┘     └──────────────────┘   │       │
│  │         │                                    ┌──────────────────┐  │       │
│  │         │                                    │   Grafana        │  │       │
│  │         │                                    │   :3001          │  │       │
│  │         │                                    └──────────────────┘  │       │
│  └─────────┼──────────────────────────────────────────────────────────┘       │
│            │                                                                     │
│  ┌─────────┼──────────────────────────────────────────────────────────┐       │
│  │  DB NETWORK (172.22.0.0/24) — Data Tier (internal, no internet)    │       │
│  │         │                                                           │       │
│  │  ┌──────▼───────┐     ┌──────────────┐     ┌──────────────────┐   │       │
│  │  │  PostgreSQL  │     │   Redis      │     │   Flower         │   │       │
│  │  │  :5432       │     │  :6379       │     │   :5555          │   │       │
│  │  └──────────────┘     └──────────────┘     └──────────────────┘   │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                               │
│  Security: All database ports bound to 127.0.0.1 only                        │
│  Backend is dual-homed: backend_network + db_network                         │
│  Frontend and DB tiers have NO direct connection                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Design Decisions and Trade-offs

### 6.1 Architecture Style: Event-Driven Microservices with Clean Architecture

**Decision**: Hybrid architecture combining Event-Driven Architecture (EDA) for real-time data, microservices for independent scaling, and Clean Architecture within each service for testability.

**Rationale**:
- EDA provides loose coupling between market data producers and AI consumers
- Clean Architecture boundaries make each service independently testable with mocked dependencies
- DDD aggregates maintain consistency boundaries for complex trading domain logic

**Trade-offs**:
- Higher initial complexity than a monolith
- Eventual consistency between services requires careful handling
- Debugging across service boundaries is harder (mitigated by OpenTelemetry tracing)

### 6.2 Authoritative Risk Engine

**Decision**: The Risk Engine has absolute override power over all other components.

**Rationale**:
- In trading systems, capital preservation is the highest priority
- Distributed consensus for risk decisions could lead to race conditions
- Single authority simplifies the safety model and audit trail

**Trade-offs**:
- Risk Engine is a single point of failure for trading decisions (mitigated by persistence and health checks)
- Risk Engine must be kept simple and thoroughly tested
- Override API must be strictly authenticated (admin role required)

### 6.3 Kafka for Event Streaming

**Decision**: Use Kafka as the primary message bus instead of RabbitMQ.

**Rationale**:
- Kafka provides stronger ordering guarantees per partition (important for tick data)
- Better throughput for high-volume market data
- Built-in log compaction enables replay and recovery
- KRaft mode eliminates Zookeeper dependency (simpler operations)

**Trade-offs**:
- Higher operational complexity than RabbitMQ
- Larger resource footprint
- RabbitMQ still available as alternative for development environments

### 6.4 Hybrid Database Strategy

**Decision**: Use PostgreSQL for OLTP, TimescaleDB for time-series, Redis for caching.

**Rationale**:
- Each database optimized for its access pattern
- TimescaleDB as PostgreSQL extension avoids operational complexity of separate TSDB
- Redis provides sub-millisecond cache lookups critical for trading

**Trade-offs**:
- Three data stores to manage and back up
- Cross-store consistency requires application-level coordination
- Memory usage for Redis must be carefully provisioned

### 6.5 Multi-Agent AI with Weighted Consensus

**Decision**: 9 specialized agents with dynamic weighted consensus instead of a single ML model.

**Rationale**:
- Specialized agents are easier to develop, test, and improve independently
- Weighted consensus provides natural explainability (which agent contributed how much)
- Dynamic weights allow the system to adapt to changing market regimes
- Individual agent failures don't halt the system (graceful degradation)

**Trade-offs**:
- Higher computational cost (9 inferences per trading decision)
- Consensus parameters require tuning per market regime
- Agent disagreement adds latency to the decision pipeline

### 6.6 RS256 JWT with Audience Binding

**Decision**: Use RS256 (asymmetric) in production with audience-based token type binding.

**Rationale**:
- Asymmetric keys allow services to verify tokens without holding the signing key
- Audience binding prevents access tokens from being used as refresh tokens and vice versa
- Short-lived access tokens (15 min) limit window of compromise

**Trade-offs**:
- Key rotation is more complex than HS256
- Token revocation requires Redis blacklist (additional infrastructure dependency)
- Refresh token rotation adds some complexity to client implementations

### 6.7 Three-Tier Docker Network Isolation

**Decision**: Three isolated Docker networks (frontend, backend, database) with the backend dual-homed.

**Rationale**:
- Database tier has no external network access (defense in depth)
- Backend is the only bridge between the web and data tiers
- Compromise of the frontend does not expose the database

**Trade-offs**:
- More complex Docker Compose configuration
- Backend must be configured with multiple network interfaces
- Some debugging tools cannot reach the database directly

### 6.8 ATR-Based Position Sizing

**Decision**: Use ATR (Average True Range) for position sizing instead of fixed lot sizes.

**Rationale**:
- ATR adapts to current market volatility
- Same strategy parameters work across different currency pairs
- Risk-per-trade stays consistent regardless of market conditions
- Aligns with institutional position sizing practices

**Trade-offs**:
- ATR is a lagging indicator (lookback period dependent)
- Very low ATR environments can lead to oversized positions (mitigated by max_position_size_pct cap)
- Requires accurate tick/candle data for correct calculation

### 6.9 Structlog for Structured Logging

**Decision**: Use structlog instead of standard Python logging.

**Rationale**:
- JSON output format integrates natively with log aggregation systems (ELK, CloudWatch)
- Context variables (request_id, user_id) are automatically bound to all log entries
- Better performance for structured logging than json.dumps on every call

**Trade-offs**:
- Additional dependency
- Team must learn structlog idioms
- Console/log-file readability requires JSON pretty-printing tools

### 6.10 Monorepo Layout

**Decision**: Single repository with `backend/`, `frontend/`, `ml/`, `infrastructure/` directories.

**Rationale**:
- Atomic commits across all layers (API change + frontend update + infra change)
- Shared CI/CD configuration
- Simplified developer onboarding (one repo to clone)
- Cross-cutting changes are visible in a single PR

**Trade-offs**:
- Larger clone size
- CI/CD must be selective about what to test on each change
- Requires discipline to maintain clean module boundaries

---

## Appendix: Key Metrics

| System | Target | Measurement |
|--------|--------|-------------|
| Signal-to-order latency | < 50ms | Prometheus histogram |
| System uptime | 99.9% | Prometheus + CloudWatch |
| Max drawdown | 15% (configurable) | Risk Engine |
| Decision explainability | 100% of trades | XAI log check |
| Recovery from failure | < 30 seconds | K8s self-healing + probes |
| AI agreement rate | > 60% | Consensus engine metric |
| Test coverage | > 80% | pytest-cov report |
| API P99 latency | < 500ms | Prometheus histogram |
