# Phase 1: Requirements & Architecture
## Institutional-Grade Autonomous AI Forex Trading Ecosystem

**Version:** 1.0.0
**Date:** 2026-06-27
**Status:** Awaiting Approval

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Subsystem Specifications](#4-subsystem-specifications)
5. [Technology Stack](#5-technology-stack)
6. [Data Architecture](#6-data-architecture)
7. [Event-Driven Architecture](#7-event-driven-architecture)
8. [Security Architecture](#8-security-architecture)
9. [Deployment Architecture](#9-deployment-architecture)
10. [Monitoring & Observability](#10-monitoring--observability)
11. [API Contracts Overview](#11-api-contracts-overview)
12. [Compliance & Regulatory](#12-compliance--regulatory)
13. [Risk Management Framework](#13-risk-management-framework)
14. [Success Criteria](#14-success-criteria)

---

## 1. Executive Summary

This document defines the complete architectural blueprint for an institutional-grade, autonomous AI Forex trading ecosystem. The system is designed for **capital preservation first**, profit generation second. Every component prioritizes reliability, explainability, and risk management over trade frequency or aggressive returns.

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Risk-First** | Every subsystem has a risk gate; the Risk Engine has absolute override authority |
| **Explainability** | Every decision produces an audit trail with confidence scores and rationale |
| **Modularity** | Clean Architecture boundaries; each component is independently testable and deployable |
| **Resilience** | Graceful degradation; no single point of failure can halt the entire system |
| **Observability** | Full distributed tracing, metrics, and centralized logging from day one |
| **Security by Default** | Zero-trust internal networking, encrypted secrets, RBAC on all endpoints |

### Success Metrics

| Metric | Target |
|--------|--------|
| Execution latency (signal → order) | < 50ms (broker-dependent) |
| System uptime | 99.9% (excluding broker maintenance) |
| Maximum drawdown | Configurable; default hard limit 15% |
| Decision explainability | 100% of trades have full XAI log |
| Time to recover from failure | < 30 seconds (automatic failover) |

---

## 2. System Overview

### 2.1 Core Functional Domains

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION LAYER                        │
│                  (Dashboard, Analytics, Alerts, API)                 │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                      ORCHESTRATION LAYER                             │
│            (Event Bus, Workflow Engine, Session Manager)             │
└──┬──────────┬──────────┬───────────┬──────────┬──────────┬─────────┘
   │          │          │           │          │          │
   ▼          ▼          ▼           ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Market│ │  AI    │ │Strategy│ │  Risk  │ │  Exec  │ │Broker  │
│ Data │ │Agents  │ │ Engine │ │ Engine │ │Engine  │ │Connect │
└──┬───┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
   │         │          │          │          │          │
   ▼         ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA & PERSISTENCE LAYER                      │
│    (PostgreSQL, Redis, TimescaleDB, Object Storage, Event Store)     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Core Workflow (Trade Lifecycle)

```
1. MARKET DATA INGESTION
   │  Real-time tick/OHLCV data from multiple brokers
   │  Multi-timeframe aggregation (M1, M5, M15, H1, H4, D1, W1)
   ▼
2. MARKET STRUCTURE ANALYSIS
   │  Session detection (Sydney → Tokyo → London → NY)
   │  Structure classification (Trending / Ranging / Volatile)
   │  SMC analysis (BOS, CHoCH, Order Blocks, FVG, Liquidity)
   ▼
3. AI AGENT CONSULTATION
   │  Each specialized agent analyzes independently
   │  Agents: Structure, Trend, Momentum, Liquidity, Sentiment, Volatility
   │  Each produces: signal + confidence + rationale
   ▼
4. SIGNAL AGGREGATION
   │  Weighted consensus across all agents
   │  Conflict detection and resolution
   │  Confidence threshold gating
   ▼
5. STRATEGY SELECTION & VALIDATION
   │  Match market regime to optimal strategy
   │  Verify strategy-specific parameters
   │  Backtest alignment check
   ▼
6. PRE-TRADE RISK VALIDATION (MANDATORY GATE)
   │  Position sizing calculation (ATR-based)
   │  Portfolio correlation check
   │  Drawdown limit verification
   │  Exposure limits per pair/sector
   │  *** RISK ENGINE HAS ABSOLUTE VETO POWER ***
   ▼
7. EXECUTION
   │  Order construction with slippage protection
   │  Broker-specific formatting
   │  Smart order routing (if multi-broker)
   │  Fill confirmation and reconciliation
   ▼
8. POST-TRADE
   │  Position monitoring
   │  Dynamic stop/take-profit management
   │  XAI log generation
   │  Performance attribution
   │  Alert generation
   ▼
9. CONTINUOUS LEARNING
   │  Outcome feedback to agents
   │  Parameter adaptation
   │  Model retraining triggers
   └  Strategy performance tracking
```

---

## 3. High-Level Architecture

### 3.1 Architecture Style: Event-Driven Microservices with Clean Architecture

The system employs a **hybrid architecture** combining:
- **Event-Driven Architecture (EDA)** for real-time data flow and decoupled communication
- **Microservices** for independent scaling and deployment of subsystems
- **Clean Architecture** within each service for testability and maintainability
- **Domain-Driven Design (DDD)** for business logic organization

### 3.2 Service Decomposition

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY                                    │
│              (FastAPI + Rate Limiting + Auth + WebSocket)                │
└─────────┬───────────────────────────────────────────────────────────────┘
          │
    ┌─────┴──────────────────────────────────────────────────────────────┐
    │                     MESSAGE BUS (RabbitMQ / Kafka)                   │
    │  Topics: market.ticks, market.ohlcv, signals, orders, positions,   │
    │          risk.alerts, system.events, xai.logs                       │
    └──┬──────────┬───────────┬──────────┬───────────┬──────────┬────────┘
       │          │           │          │           │          │
       ▼          ▼           ▼          ▼           ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │Market  │ │ AI     │ │Strategy│ │  Risk  │ │Exec    │ │Broker  │
   │Data    │ │Orch.   │ │Engine  │ │Engine  │ │Engine  │ │Gateway │
   │Service │ │Service │ │Service │ │Service │ │Service │ │Service │
   └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘
        │          │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼          ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    DATA LAYER                                    │
   │  TimescaleDB (ticks) │ PostgreSQL (state) │ Redis (cache)       │
   │  Event Store (audit) │ S3 (models/reports) │ Prometheus (metrics)│
   └─────────────────────────────────────────────────────────────────┘
```

### 3.3 Domain Model

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CORE DOMAINS                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  MARKET DOMAIN          TRADING DOMAIN          ANALYTICS DOMAIN     │
│  ├─ Tick                ├─ Order                ├─ Backtest Result    │
│  ├─ OHLCV               ├─ Position             ├─ Performance        │
│  ├─ Symbol              ├─ Deal                 ├─ Attribution        │
│  ├─ Session             ├─ Strategy             ├─ Risk Metric        │
│  └─ Structure           └─ Signal               └─ Report            │
│                                                                      │
│  RISK DOMAIN            BROKER DOMAIN           USER DOMAIN          │
│  ├─ RiskLimit           ├─ BrokerAccount        ├─ User               │
│  ├─ Exposure            ├─ Connection           ├─ Session            │
│  ├─ DrawdownState       ├─ MarketData           ├─ Preference         │
│  ├─ CorrelationMap      ├─ ExecutionReport      └─ AuditLog          │
│  └─ RiskAlert           └─ OrderBook                                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Subsystem Specifications

### 4.1 Market Data Service

**Responsibility:** Ingest, normalize, store, and distribute real-time and historical market data.

| Component | Description |
|-----------|-------------|
| **Tick Ingestion** | Real-time bid/ask streams from all connected brokers |
| **OHLCV Aggregation** | Multi-timeframe candle construction (M1→W1) |
| **Session Detector** | Identifies active trading sessions and overlaps |
| **Structure Analyzer** | SMC, liquidity zones, order blocks, FVG detection |
| **Data Normalizer** | Unified data format across different broker feeds |
| **Historical Loader** | Bulk import of historical data for backtesting |

**Data Flow:**
```
Broker Feed → Normalizer → TimescaleDB (persistence)
                     ↓
              Redis Pub/Sub (real-time distribution)
                     ↓
              AI Agents, Strategy Engine, Dashboard
```

**Key Interfaces:**
```python
class MarketDataService:
    async def subscribe_ticks(self, symbols: List[str], callback: Callable) -> None
    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Candle]
    async def get_structure(self, symbol: str) -> MarketStructure
    async def get_current_session(self) -> TradingSession
    async def get_historical(self, symbol: str, start: datetime, end: datetime) -> DataFrame
```

### 4.2 AI Orchestration Service

**Responsibility:** Coordinate multiple specialized AI agents, aggregate their outputs, and produce trade recommendations with full explainability.

#### Agent Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AI ORCHESTRATOR                                     │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                    Agent Manager                               │   │
│  │  ├─ Agent Registry (dynamic loading)                          │   │
│  │  ├─ Consensus Engine (weighted voting)                        │   │
│  │  ├─ Conflict Resolver (disagreement detection)                │   │
│  │  └─ XAI Logger (decision trail)                               │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │Structure │ │ Trend    │ │Momentum  │ │Liquidity │ │Sentiment │  │
│  │ Agent    │ │ Agent    │ │ Agent    │ │ Agent    │ │ Agent    │  │
│  │ (SMC)    │ │ (EMA/MA) │ │(RSI/MACD)│ │(Volume)  │ │(News/NLP)│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                                       │
│  ┌──────────┐ ┌──────────┐                                          │
│  │Volatility│ │ Correl.  │                                          │
│  │ Agent    │ │ Agent    │                                          │
│  │(ATR/BW)  │ │(Cross-pair)│                                        │
│  └──────────┘ └──────────┘                                          │
└──────────────────────────────────────────────────────────────────────┘
```

#### Agent Interface Contract

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class SignalDirection(Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"

@dataclass
class AgentSignal:
    agent_id: str
    direction: SignalDirection
    confidence: float          # 0.0 - 1.0
    reasoning: str             # Human-readable explanation
    supporting_data: dict      # Agent-specific metrics
    conflicts_with: List[str]  # IDs of agents with opposing signals
    timestamp: datetime

class BaseAgent(ABC):
    @abstractmethod
    async def analyze(self, market_data: MarketContext) -> AgentSignal:
        """Produce a trade signal with full reasoning."""
        pass

    @abstractmethod
    def get_weight(self, regime: MarketRegime) -> float:
        """Return agent weight for current market regime."""
        pass

    @abstractmethod
    def required_data(self) -> List[str]:
        """List of data dependencies."""
        pass
```

#### Consensus Algorithm

```python
class ConsensusEngine:
    """
    Weighted voting with conflict detection.

    Final confidence = Σ(agent_weight × agent_confidence) / Σ(agent_weight)
    
    Requires minimum 60% weighted agreement for signal generation.
    Maximum conflict threshold: if >30% of weight conflicts, signal is rejected.
    """

    MIN_AGREEMENT_THRESHOLD = 0.60
    MAX_CONFLICT_THRESHOLD = 0.30
    MIN_AGENTS_RESPONDING = 4
```

### 4.3 Strategy Engine

**Responsibility:** Map market regimes to optimal strategies, manage strategy lifecycle, and validate trade ideas.

#### Strategy Registry

| Strategy | Market Regime | Description |
|----------|---------------|-------------|
| **Trend Following** | Strong Trend | Ride momentum with trailing stops |
| **Mean Reversion** | Range-bound | Fade extremes at support/resistance |
| **Scalping** | High Liquidity, Low Vol | Quick entries/exits on micro-structure |
| **Breakout** | Consolidation | Enter on structure break with volume confirmation |
| **Grid Trading** | Ranging, Low Volatility | Systematic buy/sell at intervals |
| **Sentiment Fade** | Extreme Sentiment | Contrarian on extreme positioning |

```python
class StrategyEngine:
    async def select_strategy(self, regime: MarketRegime, context: MarketContext) -> Strategy
    async def validate_trade(self, signal: TradeSignal, strategy: Strategy) -> ValidationResult
    async def get_parameters(self, strategy: Strategy, symbol: str) -> StrategyParameters
    async def record_outcome(self, trade_id: str, outcome: TradeOutcome) -> None
```

### 4.4 Risk Engine (AUTHORITATIVE)

**Responsibility:** The single most critical subsystem. Has **absolute override authority** over all other components. Can veto any trade, force position closure, and modify execution parameters.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    RISK ENGINE (ABSOLUTE AUTHORITY)                   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                   PRE-TRADE CHECKS                           │     │
│  │  ├─ Position Size Validation (Kelly/ATR-based)              │     │
│  │  ├─ Portfolio Exposure Check (per pair, per currency)       │     │
│  │  ├─ Correlation Matrix Validation                           │     │
│  │  ├─ Drawdown Limit Verification (daily, weekly, monthly)    │     │
│  │  ├─ Maximum Open Positions Check                            │     │
│  │  ├─ Spread/Slippage Tolerance                               │     │
│  │  └─ Strategy Agreement Requirement                          │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                   REAL-TIME MONITORING                       │     │
│  │  ├─ Position P&L Tracking                                   │     │
│  │  ├─ Dynamic Stop-Loss Management (ATR-trailing)             │     │
│  │  ├─ Correlation Breakdown Detection                         │     │
│  │  ├─ Volatility Spike Response                               │     │
│  │  └─ Emergency Position Liquidation                          │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                   POST-TRADE ANALYSIS                        │     │
│  │  ├─ Performance Attribution                                 │     │
│  │  ├─ Risk-Adjusted Return Calculation                        │     │
│  │  ├─ Drawdown State Update                                   │     │
│  │  └─ Strategy Score Adjustment                               │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  OVERRIDE CAPABILITIES:                                               │
│  ✦ Can REJECT any trade from any source                              │
│  ✦ Can FORCE close any position                                      │
│  ✦ Can REDUCE position size                                          │
│  ✦ Can BLOCK trading during extreme conditions                       │
│  ✦ Can EMERGENCY liquidate all positions                             │
│  ✦ CANNOT be overridden by any other component                       │
└──────────────────────────────────────────────────────────────────────┘
```

#### Risk Limits Configuration

```python
@dataclass
class RiskLimits:
    # Position Limits
    max_position_size_pct: float = 0.02       # 2% of equity per position
    max_total_exposure_pct: float = 0.20      # 20% total exposure
    max_positions: int = 10
    
    # Drawdown Limits
    daily_drawdown_limit_pct: float = 0.03    # 3% daily
    weekly_drawdown_limit_pct: float = 0.05   # 5% weekly
    monthly_drawdown_limit_pct: float = 0.10  # 10% monthly
    max_drawdown_limit_pct: float = 0.15      # 15% total (circuit breaker)
    
    # Exposure Limits
    max_exposure_per_pair_pct: float = 0.05   # 5% per pair
    max_correlated_exposure_pct: float = 0.10 # 10% in correlated pairs
    
    # Execution Limits
    max_slippage_pips: float = 3.0
    max_spread_pips: float = 5.0
    max_spread_multiplier: float = 2.0        # Max spread vs average
    
    # Circuit Breakers
    max_consecutive_losses: int = 5
    cooldown_after_circuit_breaker_minutes: int = 60
```

### 4.5 Execution Engine

**Responsibility:** Translate approved trade signals into broker-specific orders, manage order lifecycle, and handle fill reconciliation.

```
Approved Signal → Order Construction → Validation → Submission → Monitoring
                     │                   │              │            │
                     │                   │              │            ├─ Fill Confirmation
                     │                   │              │            ├─ Partial Fill Handling
                     │                   │              │            └─ Rejection Handling
                     │                   │              │
                     │                   │              └─ Smart Order Router
                     │                   │                 (multi-broker optimization)
                     │                   │
                     │                   └─ Pre-submission Validation
                     │                      (price, size, time-in-force)
                     │
                     └─ Order Type Selection
                        (Market, Limit, Stop, Trailing Stop, OCO)
```

### 4.6 Broker Gateway Service

**Responsibility:** Provide a unified interface to multiple brokers with auto-discovery, connection management, and protocol translation.

#### Supported Brokers

| Broker | Protocol | API Type | Notes |
|--------|----------|----------|-------|
| **MetaTrader 4** | Socket | MQL4 EA | Via REST bridge (mt-manager) |
| **MetaTrader 5** | Socket | MQL5 EA | Native Python adapter |
| **OANDA** | REST + Streaming | v20 API | Best for development |
| **FXCM** | REST + WebSocket | Trading API | Good documentation |
| **cTrader** | Open API | gRPC + WebSocket | Modern, low-latency |
| **Interactive Brokers** | TWS API | Python client | Most instruments |

```python
class BrokerPlugin(ABC):
    @abstractmethod
    async def connect(self, credentials: BrokerCredentials) -> bool: pass
    
    @abstractmethod
    async def subscribe_market_data(self, symbols: List[str]) -> None: pass
    
    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult: pass
    
    @abstractmethod
    async def modify_order(self, order_id: str, modifications: OrderMod) -> OrderResult: pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]: pass
    
    @abstractmethod
    async def get_account_info(self) -> AccountInfo: pass
    
    @abstractmethod
    async def get_order_history(self, since: datetime) -> List[Order]: pass
```

---

## 5. Technology Stack

### 5.1 Stack Overview

| Layer | Technology | Justification |
|-------|-----------|---------------|
| **Frontend** | Next.js 15 + TypeScript | SSR, WebSocket support, component ecosystem |
| **UI Framework** | Tailwind CSS + shadcn/ui | Rapid, consistent UI development |
| **Charts** | TradingView Lightweight Charts + D3.js | Professional financial visualization |
| **Backend Core** | Python 3.12+ + FastAPI | Async support, type hints, performance |
| **Inter-service** | gRPC | High-performance internal communication |
| **Message Bus** | RabbitMQ (primary) | Reliable message delivery, topic exchange |
| **Real-time Streaming** | Apache Kafka | High-throughput market data ingestion |
| **Primary Database** | PostgreSQL 16 | ACID compliance, JSON support, maturity |
| **Time-series Data** | TimescaleDB (PostgreSQL extension) | Optimized for tick/OHLCV data |
| **Cache** | Redis 7 | Real-time caching, pub/sub, rate limiting |
| **AI/ML Framework** | PyTorch + Scikit-learn | Model training, inference, ensemble methods |
| **Hyperparameter Tuning** | Optuna | Efficient parameter optimization |
| **Model Explainability** | SHAP + LIME | Feature importance, decision explanations |
| **Containerization** | Docker + Docker Compose | Consistent environments |
| **Orchestration** | Kubernetes (production) | Auto-scaling, self-healing |
| **Infrastructure** | Terraform + AWS | Infrastructure as code, reproducibility |
| **CI/CD** | GitHub Actions | Integrated with code repository |
| **Monitoring** | Prometheus + Grafana | Metrics collection, visualization |
| **Logging** | ELK Stack (Elasticsearch, Logstash, Kibana) | Centralized log aggregation |
| **Tracing** | OpenTelemetry + Jaeger | Distributed request tracing |
| **Secrets** | HashiCorp Vault | Encrypted secrets management |

### 5.2 Python Package Dependencies (Core)

```toml
[project]
name = "forex-ai-trading-system"
version = "0.1.0"
requires-python = ">=3.12"

[tool.poetry.dependencies]
# Web Framework
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.30"}
python-jose = {extras = ["cryptography"], version = "^3.3"}
passlib = {extras = ["bcrypt"], version = "^1.7"}
python-multipart = "^0.0.9"

# Database
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.29"
alembic = "^1.13"
redis = {extras = ["hiredis"], version = "^5.0"}
timescaledb = "^0.1"

# Message Bus
aio-pika = "^9.4"
confluent-kafka = "^2.3"

# gRPC
grpcio = "^1.62"
grpcio-tools = "^1.62"

# AI/ML
torch = "^2.3"
scikit-learn = "^1.4"
xgboost = "^2.0"
optuna = "^3.6"
shap = "^0.45"
pandas = "^2.2"
numpy = "^1.26"
ta-lib = "^0.4"  # Technical analysis

# Monitoring
prometheus-client = "^0.20"
opentelemetry-api = "^1.24"
opentelemetry-sdk = "^1.24"
opentelemetry-exporter-jaeger = "^1.21"

# Utilities
pydantic = {extras = ["email"], version = "^2.6"}
httpx = "^0.27"
websockets = "^12.0"
python-dotenv = "^1.0"
structlog = "^24.1"

# Testing
pytest = "^8.1"
pytest-asyncio = "^0.23"
pytest-cov = "^4.1"
hypothesis = "^6.98"
```

---

## 6. Data Architecture

### 6.1 Database Design Principles

- **Separation of Concerns:** Different data stores for different access patterns
- **Immutable Events:** Market data and trade events are append-only
- **Audit Trail:** Every state change is recorded with timestamp and source
- **Time-Series Optimization:** Tick data uses TimescaleDB hypertables

### 6.2 Data Stores

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │   PostgreSQL     │     │   TimescaleDB    │                    │
│  │   (OLTP)         │     │   (Time-Series)  │                    │
│  ├─────────────────┤     ├─────────────────┤                    │
│  │ • Users          │     │ • Tick data       │                    │
│  │ • Accounts       │     │ • OHLCV candles   │                    │
│  │ • Orders         │     │ • Order book snaps│                    │
│  │ • Positions      │     │ • Volume data     │                    │
│  │ • Strategies     │     │ • Volatility data │                    │
│  │ • Risk configs   │     │                   │                    │
│  │ • Audit logs     │     │ Retention: 2 years│                    │
│  │ • AI decisions   │     │                   │                    │
│  └─────────────────┘     └─────────────────┘                    │
│                                                                   │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │   Redis           │     │   S3 / MinIO     │                    │
│  │   (Cache/PubSub)  │     │   (Object Store)  │                    │
│  ├─────────────────┤     ├─────────────────┤                    │
│  │ • Current prices  │     │ • Trained models  │                    │
│  │ • Session state   │     │ • Backtest results │                    │
│  │ • Rate limiting   │     │ • Reports (PDF)   │                    │
│  │ • Pub/Sub channels│     │ • Historical data  │                    │
│  │ • Temporary state │     │   archives        │                    │
│  └─────────────────┘     └─────────────────┘                    │
│                                                                   │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │   Event Store     │     │   Elasticsearch  │                    │
│  │   (Append-Only)   │     │   (Logs)         │                    │
│  ├─────────────────┤     ├─────────────────┤                    │
│  │ • Trade events    │     │ • Application logs│                    │
│  │ • System events   │     │ • XAI decision   │                    │
│  │ • Risk events     │     │   logs           │                    │
│  │ • Market events   │     │ • Audit logs     │                    │
│  └─────────────────┘     └─────────────────┘                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Key Entity Relationships

```
User ──1:N──▶ BrokerAccount ──1:N──▶ Order
                                      │
                                      ├──1:1──▶ Deal (fill)
                                      │
                                      └──N:1──▶ Strategy
                                      
BrokerAccount ──1:N──▶ Position ──N:M──▶ Symbol

RiskEngine ──1:N──▶ RiskAlert
RiskEngine ──1:1──▶ RiskState (current drawdown, exposure, etc.)

AIOrchestrator ──1:N──▶ AgentSignal ──N:1──▶ AIDecision ──1:1──▶ Order
```

---

## 7. Event-Driven Architecture

### 7.1 Event Bus Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVENT BUS (RabbitMQ)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  EXCHANGES:                                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ market.data (topic)                                        │  │
│  │   ├── market.ticks.{symbol}                               │  │
│  │   ├── market.ohlcv.{symbol}.{timeframe}                   │  │
│  │   └── market.structure.{symbol}                           │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ trading.signals (fanout)                                   │  │
│  │   ├── signal.generated.{strategy}                         │  │
│  │   ├── signal.approved                                     │  │
│  │   └── signal.rejected                                     │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ trading.orders (direct)                                    │  │
│  │   ├── order.new                                           │  │
│  │   ├── order.filled                                        │  │
│  │   ├── order.partially_filled                              │  │
│  │   ├── order.cancelled                                     │  │
│  │   └── order.rejected                                      │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ risk.events (topic)                                        │  │
│  │   ├── risk.alert.{level} (info, warning, critical)       │  │
│  │   ├── risk.override                                       │  │
│  │   └── risk.circuit_breaker                                │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │ system.events (topic)                                      │  │
│  │   ├── system.health                                       │  │
│  │   ├── system.error                                        │  │
│  │   └── system.audit                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Event Schema (CloudEvents Compatible)

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

class CloudEvent(BaseModel):
    specversion: str = "1.0"
    id: UUID = Field(default_factory=uuid4)
    source: str                          # e.g., "trading.risk-engine"
    type: str                            # e.g., "risk.alert.critical"
    datacontenttype: str = "application/json"
    time: datetime
    data: dict[str, Any]                 # Event payload

class MarketTickEvent(CloudEvent):
    type: str = "market.tick"
    data: dict = Field(..., schema={
        "symbol": str,
        "bid": float,
        "ask": float,
        "volume": float,
        "timestamp": datetime
    })

class TradeSignalEvent(CloudEvent):
    type: str = "trading.signal.generated"
    data: dict = Field(..., schema={
        "signal_id": UUID,
        "strategy": str,
        "symbol": str,
        "direction": str,  # "long" | "short"
        "entry_price": float,
        "stop_loss": float,
        "take_profit": float,
        "confidence": float,
        "agents": list[dict],  # Agent signals
        "rationale": str
    })

class RiskOverrideEvent(CloudEvent):
    type: str = "risk.override"
    data: dict = Field(..., schema={
        "override_id": UUID,
        "target_order_id": Optional[UUID],
        "target_position_id": Optional[UUID],
        "action": str,  # "reject_order" | "close_position" | "reduce_size"
        "reason": str,
        "risk_state": dict
    })
```

---

## 8. Security Architecture

### 8.1 Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    AUTHENTICATION                         │    │
│  │  • JWT tokens (RS256) with short expiry (15 min)        │    │
│  │  • Refresh tokens (7 days) with rotation                │    │
│  │  • MFA (TOTP) for sensitive operations                  │    │
│  │  • API keys for programmatic access                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    AUTHORIZATION                          │    │
│  │  • Role-Based Access Control (RBAC)                      │    │
│  │  • Roles: Viewer, Trader, Admin, SuperAdmin              │    │
│  │  • Resource-level permissions                            │    │
│  │  • API scope restrictions                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    DATA PROTECTION                        │    │
│  │  • TLS 1.3 for all communications                       │    │
│  │  • AES-256 encryption at rest for secrets                │    │
│  │  • HashiCorp Vault for secrets management               │    │
│  │  • No secrets in code or environment variables          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    INFRASTRUCTURE SECURITY               │    │
│  │  • VPC with private subnets for services                │    │
│  │  • Security groups / firewall rules                     │    │
│  │  • WAF at API gateway level                             │    │
│  │  • DDoS protection (AWS Shield)                         │    │
│  │  • Dependabot for dependency scanning                   │    │
│  │  • Trivy for container image scanning                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    MONITORING & RESPONSE                  │    │
│  │  • Failed login attempt alerting                        │    │
│  │  • Anomaly detection on API usage                       │    │
│  │  • Audit trail for all state changes                    │    │
│  │  • Incident response runbook                            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 RBAC Permission Matrix

| Resource | Viewer | Trader | Admin | SuperAdmin |
|----------|--------|--------|-------|------------|
| View Dashboard | ✅ | ✅ | ✅ | ✅ |
| View Trades | ✅ | ✅ | ✅ | ✅ |
| Execute Trades | ❌ | ✅ | ✅ | ✅ |
| Modify Strategy | ❌ | ❌ | ✅ | ✅ |
| Modify Risk Limits | ❌ | ❌ | ✅ | ✅ |
| View API Keys | ❌ | ❌ | ✅ | ✅ |
| Manage Users | ❌ | ❌ | ❌ | ✅ |
| System Config | ❌ | ❌ | ❌ | ✅ |

---

## 9. Deployment Architecture

### 9.1 Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    AWS CLOUD INFRASTRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────── VPC (10.0.0.0/16) ──────────────────┐ │
│  │                                                              │ │
│  │  ┌──────────────── PUBLIC SUBNET ──────────────────────┐   │ │
│  │  │  • ALB (Application Load Balancer)                   │   │ │
│  │  │  • NAT Gateway                                       │   │ │
│  │  │  • Bastion Host                                      │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                                                              │ │
│  │  ┌──────────────── PRIVATE SUBNET (App) ───────────────┐   │ │
│  │  │  • EKS Cluster (Kubernetes)                          │   │ │
│  │  │    ├─ API Gateway Pod                                │   │ │
│  │  │    ├─ Market Data Service Pod                        │   │ │
│  │  │    ├─ AI Orchestration Pod                           │   │ │
│  │  │    ├─ Strategy Engine Pod                            │   │ │
│  │  │    ├─ Risk Engine Pod                                │   │ │
│  │  │    ├─ Execution Engine Pod                           │   │ │
│  │  │    ├─ Broker Gateway Pod                             │   │ │
│  │  │    ├─ Analytics Pod                                  │   │ │
│  │  │    └─ Notification Pod                               │   │ │
│  │  │  • ElastiCache (Redis)                               │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                                                              │ │
│  │  ┌──────────────── PRIVATE SUBNET (Data) ──────────────┐   │ │
│  │  │  • RDS PostgreSQL (Multi-AZ)                         │   │ │
│  │  │  • Amazon MSK (Kafka)                                │   │ │
│  │  │  • S3 Buckets (models, logs, reports)                │   │ │
│  │  │  • Amazon MQ (RabbitMQ)                              │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                   │
│  EXTERNAL SERVICES:                                              │
│  • HashiCorp Vault (secrets)                                     │
│  • CloudWatch (metrics, logs)                                    │
│  • AWS WAF (web application firewall)                            │
│  • AWS Shield (DDoS protection)                                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Kubernetes Service Mesh

```yaml
# Service configuration pattern
apiVersion: apps/v1
kind: Deployment
metadata:
  name: risk-engine
  namespace: trading
spec:
  replicas: 3              # Minimum 3 for HA
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: risk-engine
          image: registry.example.com/risk-engine:v1.0.0
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 3
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-secrets
                  key: url
```

---

## 10. Monitoring & Observability

### 10.1 Observability Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY STACK                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  METRICS (Prometheus → Grafana)                                  │
│  ├─ System: CPU, Memory, Disk, Network                          │
│  ├─ Application: Request rate, Latency, Errors                  │
│  ├─ Trading: P&L, Win Rate, Drawdown, Sharpe                    │
│  ├─ Risk: Exposure, Correlation, VaR                            │
│  └─ Business: Trades/day, Signal confidence, Agent agreement    │
│                                                                   │
│  LOGGING (Fluentd → Elasticsearch → Kibana)                      │
│  ├─ Structured JSON logging                                     │
│  ├─ Request tracing (correlation IDs)                           │
│  ├─ XAI decision logs                                           │
│  └─ Audit trail                                                 │
│                                                                   │
│  TRACING (OpenTelemetry → Jaeger)                                │
│  ├─ Distributed request tracing across services                 │
│  ├─ Latency analysis per service hop                            │
│  └─ Error propagation tracking                                  │
│                                                                   │
│  ALERTING (PagerDuty / Slack)                                    │
│  ├─ Critical: System down, Risk breach, Execution failure       │
│  ├─ Warning: High latency, Unusual activity, Model drift       │
│  └─ Info: Daily summary, Performance report                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Key Metrics & Dashboards

| Dashboard | Key Metrics |
|-----------|-------------|
| **System Health** | Service uptime, Request latency p99, Error rate, Queue depth |
| **Trading Performance** | Daily P&L, Cumulative returns, Win/loss ratio, Expectancy |
| **Risk Monitor** | Current drawdown, VaR, Position exposure, Correlation matrix |
| **Agent Performance** | Signal confidence distribution, Agent agreement rate, Accuracy |
| **Execution Quality** | Slippage, Fill rate, Order-to-fill latency, Rejection rate |

---

## 11. API Contracts Overview

### 11.1 REST API Structure

```
/api/v1/
├── /auth
│   ├── POST /login
│   ├── POST /refresh
│   ├── POST /mfa/enable
│   └── POST /mfa/verify
├── /accounts
│   ├── GET /                    (list broker accounts)
│   ├── POST /                   (add broker account)
│   ├── GET /{id}                (account details)
│   ├── GET /{id}/positions      (current positions)
│   └── GET /{id}/orders         (order history)
├── /trading
│   ├── POST /signal             (manual signal submission)
│   ├── GET /signals             (signal history)
│   ├── GET /positions           (all positions)
│   └── GET /orders              (all orders)
├── /market
│   ├── GET /symbols             (available symbols)
│   ├── GET /{symbol}/ticks      (recent ticks)
│   ├── GET /{symbol}/candles    (OHLCV data)
│   └── GET /{symbol}/structure  (market structure)
├── /ai
│   ├── GET /agents              (agent status)
│   ├── GET /decisions           (decision history)
│   ├── GET /decisions/{id}      (XAI detail)
│   └── GET /performance         (agent accuracy)
├── /strategy
│   ├── GET /strategies          (active strategies)
│   ├── GET /{id}/performance    (strategy metrics)
│   └── PUT /{id}/parameters     (update parameters)
├── /risk
│   ├── GET /limits              (current risk limits)
│   ├── PUT /limits              (update risk limits)
│   ├── GET /alerts              (risk alerts)
│   └── GET /state               (current risk state)
├── /analytics
│   ├── GET /performance         (portfolio performance)
│   ├── GET /attribution         (P&L attribution)
│   └── GET /reports             (generated reports)
├── /backtest
│   ├── POST /run                (start backtest)
│   ├── GET /results             (backtest results)
│   └── GET /results/{id}        (specific result)
└── /system
    ├── GET /health              (system health)
    ├── GET /health/detailed     (per-service health)
    └── GET /metrics             (system metrics)
```

### 11.2 WebSocket Endpoints

```
WS /ws/market/{symbol}           Real-time tick data
WS /ws/orders/{account_id}       Order status updates
WS /ws/positions/{account_id}    Position updates
WS /ws/signals                   Live signal feed
WS /ws/alerts                    System alerts
WS /ws/dashboard                 Dashboard real-time updates
```

---

## 12. Compliance & Regulatory

### 12.1 Data Retention

| Data Type | Retention Period | Storage |
|-----------|-----------------|---------|
| Trade records | 7 years | PostgreSQL + S3 archive |
| Market data (ticks) | 2 years | TimescaleDB |
| Audit logs | 5 years | Elasticsearch + S3 |
| User data | Duration + 1 year | PostgreSQL |
| System logs | 90 days | Elasticsearch |

### 12.2 Audit Requirements

- Every trade must have a complete decision trail
- All risk overrides must be logged with justification
- User actions must be traceable to individual accounts
- System configuration changes must require authorization

---

## 13. Risk Management Framework

### 13.1 Risk Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    RISK HIERARCHY                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  LEVEL 1: SYSTEM LEVEL                                           │
│  └─ Maximum portfolio drawdown (hard stop)                      │
│     If triggered: Close ALL positions, halt trading             │
│                                                                   │
│  LEVEL 2: PORTFOLIO LEVEL                                        │
│  └─ Total exposure limits, correlation limits                   │
│     If exceeded: Block new positions                            │
│                                                                   │
│  LEVEL 3: STRATEGY LEVEL                                         │
│  └─ Per-strategy allocation, win rate monitoring                │
│     If degraded: Reduce strategy weight or pause                │
│                                                                   │
│  LEVEL 4: POSITION LEVEL                                         │
│  └─ Per-position sizing, stop-loss, take-profit                 │
│     If breached: Close or modify position                       │
│                                                                   │
│  LEVEL 5: EXECUTION LEVEL                                        │
│  └─ Slippage limits, spread tolerance, fill requirements        │
│     If exceeded: Reject or modify order                         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 13.2 Position Sizing Algorithm

```python
def calculate_position_size(
    account_equity: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_loss_price: float,
    symbol: str,
    current_spread: float
) -> float:
    """
    ATR-based position sizing with volatility adjustment.
    
    Steps:
    1. Calculate risk amount in account currency
    2. Calculate stop distance (including spread)
    3. Apply volatility adjustment factor
    4. Calculate position size in lots
    5. Validate against risk limits
    """
    risk_amount = account_equity * (risk_per_trade_pct / 100)
    
    stop_distance_pips = abs(entry_price - stop_loss_price) * pip_multiplier[symbol]
    adjusted_stop = stop_distance_pips + current_spread
    
    # Volatility adjustment: reduce size in high-volatility conditions
    vol_adjustment = min(1.0, avg_atr[symbol] / current_atr[symbol])
    
    position_size = (risk_amount * vol_adjustment) / (adjusted_stop * pip_value[symbol])
    
    return round(position_size, 2)  # Round to broker precision
```

---

## 14. Success Criteria

### 14.1 Phase 1 Approval Checklist

| Item | Status | Notes |
|------|--------|-------|
| System architecture defined | ✅ | Document complete |
| All subsystems specified | ✅ | 6 core services defined |
| Technology stack selected | ✅ | Justified selections |
| Data architecture designed | ✅ | 5 data stores specified |
| Event-driven architecture defined | ✅ | Topics and schemas |
| Security architecture defined | ✅ | RBAC, encryption, MFA |
| Deployment architecture defined | ✅ | AWS EKS with Terraform |
| Monitoring strategy defined | ✅ | Metrics, logs, traces |
| API contracts outlined | ✅ | REST + WebSocket |
| Risk management framework defined | ✅ | 5-level hierarchy |

---

## Next Steps (Pending Approval)

Upon approval of this Phase 1 document, **Phase 2: Repository & Project Structure** will:

1. Initialize the Git repository with proper branching strategy
2. Create the project directory structure following Clean Architecture
3. Set up the monorepo structure for frontend and backend
4. Configure development tooling (linting, formatting, type checking)
5. Set up GitHub Actions CI/CD pipelines
6. Create Docker development environment
7. Initialize database migrations
8. Write project-level documentation (README, CONTRIBUTING, etc.)

---

**Document prepared by:** Multi-disciplinary Engineering Team
**Review status:** Pending User Approval
**Next phase:** Phase 2 - Repository & Project Structure
