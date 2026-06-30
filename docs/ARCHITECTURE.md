# Architecture – Institutional Forex AI Trading Platform

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL WORLD                                  │
│   Brokers (OANDA, MT4/5)    News Feeds    Market Data Vendors           │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                          INGESTION LAYER                                │
│   Broker Plugins (gRPC)   ◄──────────────►  Market Data Service         │
│   (OANDA / MT4 / MT5 / Paper)              (Tick, Candle, Calendar)     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │  Kafka Topics
┌───────────────────────────────────▼─────────────────────────────────────┐
│                          AI ANALYSIS LAYER                              │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              AI Orchestrator (9 Agents)                         │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │   │
│   │  │ Trend    │ │Market    │ │Liquidity │ │   Volatility     │   │   │
│   │  │ Agent    │ │Structure │ │ Agent    │ │    Agent         │   │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │   │
│   │  │Sentiment │ │SmartMoney│ │  Risk AI │ │  Entry / Exit    │   │   │
│   │  │  Agent   │ │  Agent   │ │  Agent   │ │    Agents        │   │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │   │
│   │                        ▼                                        │   │
│   │            ┌───────────────────────┐                            │   │
│   │            │   Consensus Engine    │  Weighted vote             │   │
│   │            │   agreement_threshold │  + conflict detection      │   │
│   │            └───────────────────────┘                            │   │
│   │                        ▼                                        │   │
│   │            ┌───────────────────────┐                            │   │
│   │            │    XAI Explainer      │  SHAP-based rationale      │   │
│   │            └───────────────────────┘                            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │  OrchestratorResult
┌───────────────────────────────────▼─────────────────────────────────────┐
│                         STRATEGY LAYER                                  │
│   StrategyRegistry ──► StrategyEngine ──► PositionSizer                 │
│   (7 strategies: TrendFollowing, Pullback, Breakout, MeanReversion,     │
│    Scalping, LondonOpen, AsianRange)                                    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │  TradeSignal
┌───────────────────────────────────▼─────────────────────────────────────┐
│                         RISK ENGINE (Authoritative)                     │
│   Circuit Breaker ◄── DrawdownMonitor ◄── PositionMonitor               │
│   NO OTHER COMPONENT CAN OVERRIDE THE RISK ENGINE                       │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │  RiskAssessment (approved/rejected)
┌───────────────────────────────────▼─────────────────────────────────────┐
│                         EXECUTION ENGINE                                │
│   OrderManager ──► BrokerGateway ──► TrailingStop Manager               │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                        INFRASTRUCTURE LAYER                             │
│   PostgreSQL/TimescaleDB   Redis Cache   Kafka Message Bus              │
│   Prometheus Metrics       Jaeger Tracing    Grafana Dashboards         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. AI Multi-Agent System

### Architecture

The AI layer consists of **9 specialised agents** and a **Consensus Engine**.

| Agent | Focus | Weight (Trending) |
|---|---|---|
| `market_structure` | ICT/SMC swing highs/lows, BOS, CHoCH | 0.90 |
| `trend` | EMA20/50/200, ADX, MACD | 0.90 |
| `liquidity` | Order blocks, FVGs, liquidity sweeps | 0.80 |
| `volatility` | ATR, Bollinger Bands, VWAP spread | 0.80 |
| `sentiment` | RSI, CoT positioning, momentum | 0.75 |
| `smart_money` | Discount/Premium zone, equilibrium | 0.80 |
| `risk_ai` | Spread, drawdown, news veto | 0.95 (all regimes) |
| `entry_ai` | Micro-structure entry timing, R:R | 0.85 (all regimes) |
| `exit_ai` | Trail stop, TP, reversal, session-end | 0.85 (all regimes) |

### How Agents Work

1. **Analyse**: Each agent receives a `MarketContext` (candles, regime, metadata).
2. **Vote**: Each agent emits an `AgentSignal` with `direction` (LONG/SHORT/NEUTRAL) and `confidence` (0–1).
3. **Weigh**: Weights are regime-dependent (e.g., `trend` agent gets high weight in TRENDING_UP).
4. **Aggregate**: `ConsensusEngine` computes a weighted vote; if `agreement_ratio >= 0.60` the signal is actionable.
5. **Explain**: `TradeExplainer` generates a SHAP-style narrative showing which agents drove the decision.

### Consensus Engine

```python
# Pseudo-code
weighted_long  = sum(w * conf for agent, w, conf if direction == LONG)
weighted_short = sum(w * conf for agent, w, conf if direction == SHORT)
agreement_ratio = max(weighted_long, weighted_short) / total_weight
is_actionable = agreement_ratio >= threshold AND risk_agent != NEUTRAL
```

### Risk Agent Veto

The `RiskAgent` (agent_id=`risk_ai`) acts as an independent circuit-breaker within the AI layer:
- If spread > 5 pips → NEUTRAL (no trade)
- If drawdown > 5% → NEUTRAL
- If high-impact news within 30 min → NEUTRAL
- If open_positions >= limit → NEUTRAL

Even if all other 8 agents vote LONG unanimously, a NEUTRAL from `risk_ai` prevents a trade.

---

## 3. Risk Management

### Circuit Breaker

```
Daily Drawdown ≥ 3%  ──► WARNING alert
Max Drawdown   ≥ 15% ──► CIRCUIT BREAKER ACTIVATED
                         (all trading halted for cooldown_minutes)
                         (emergency_liquidate available to admin)
```

### Position Limits

| Limit | Default | Override |
|---|---|---|
| `max_position_size_pct` | 2% of equity | Admin via PUT /risk/config |
| `max_total_exposure_pct` | 20% of equity | Admin |
| `max_positions` | 10 concurrent | Admin |
| `max_consecutive_losses` | 5 | Admin |
| `max_spread_pips` | 5 pips | Admin |

### Position Sizing (PositionSizer)

```
risk_amount  = account_balance × risk_pct / 100
pip_value    = contract_size × pip_size  (÷ price for JPY pairs)
lot_size     = risk_amount / (stop_loss_pips × pip_value)
lot_size     = clamp(lot_size, 0.01, max_allowed)
```

### Trailing Stop Logic (ExecutionEngine)

| Threshold | Action |
|---|---|
| Price moves +1×ATR in favour | Move SL to breakeven |
| Price moves +2×ATR | Partial close 33% |
| Price moves +3×ATR | Trail at 2×ATR distance |
| Holding time > `max_holding_minutes` | Force close |

---

## 4. Strategy Engine

### Available Strategies

| Strategy | Best Regime | Key Filters |
|---|---|---|
| `TrendFollowing` | TRENDING_UP, TRENDING_DOWN | EMA alignment, ADX ≥ 25, R:R ≥ 2 |
| `Pullback` | TRENDING_UP, TRENDING_DOWN | Entry within 10 pips of EMA20, RSI < 65 |
| `Breakout` | TRENDING_UP, VOLATILE | Volume × 1.2 avg, entry above resistance |
| `MeanReversion` | RANGING | Entry at Bollinger lower/upper, RSI oversold/overbought |
| `Scalping` | Any (London/NY overlap only) | Spread ≤ 1.5 pips, order flow imbalance |
| `LondonOpen` | TRENDING | Time 07:00–09:00 UTC, break of Asian high/low |
| `AsianRange` | RANGING, LOW_VOLATILITY | Time 00:00–09:00 UTC, entry at range extreme |

### Strategy Selection

```python
# StrategyRegistry.get_best_for_regime(regime, performance_stats)
1. Filter strategies that include `regime` in their optimal_regimes list
2. Sort by historical win_rate and profit_factor (if performance stats available)
3. Return highest-ranked strategy (fallback: first match)
```

---

## 5. Trade Execution Flow (Step-by-Step)

```
1. AI Orchestrator analyses MarketContext → OrchestratorResult
2. ConsensusEngine.is_actionable == True AND direction != NEUTRAL
3. StrategyEngine selects best strategy for current regime
4. Strategy.validate_signal(ctx, signal) → ValidationResult
5. PositionSizer.calculate_size(balance, risk_pct, entry, sl, symbol) → lots
6. RiskEngine.assess_trade(symbol, side, size, entry) → RiskAssessment
   ├── REJECTED → log, alert, skip
   └── APPROVED → continue
7. ExecutionEngine.process_signal(signal, broker_account_id)
   ├── Check news blackout window
   ├── Check spread ≤ max_spread_pips
   ├── Check correlated position limit
   └── BrokerGateway.place_order(symbol, side, lots, sl, tp)
8. Position opened → _TrackedPosition added to in-memory store
9. Background loop: manage_position(pid, current_price) every tick
   ├── move_breakeven → update SL
   ├── partial_close → reduce position
   ├── trail_stop → new SL
   └── close → remove from store
10. Analytics updated: win/loss, PnL, strategy performance stats
```

---

## 6. Broker Integration (Plugin Architecture)

```
BrokerPlugin (abstract)
├── OANDAPlugin      → REST API v20, streaming prices
├── MT4Plugin        → Expert Advisor (TCP socket bridge)
├── MT5Plugin        → MetaTrader5 Python library
└── PaperTradingPlugin → In-memory simulated fills (for testing/backtesting)
```

### Plugin Interface

```python
class BrokerPlugin(ABC):
    async def connect() -> None
    async def disconnect() -> None
    async def get_account_info() -> AccountInfo
    async def place_order(symbol, side, quantity, ...) -> dict
    async def close_position(position_id, ...) -> dict
    async def get_open_positions() -> list[Position]
    async def subscribe_prices(symbols, callback) -> None
```

Plugins are registered via `BrokerRegistry` and injected into `ExecutionEngine`.

---

## 7. Data Flow

### Kafka Topics

| Topic | Producer | Consumer | Content |
|---|---|---|---|
| `market.ticks` | Broker Plugins | AI Agents, Market Data Service | Bid/Ask ticks |
| `market.candles` | Market Data Service | Strategy Engine, AI Agents | OHLCV |
| `trading.orders` | Execution Engine | Order Monitor | Order lifecycle |
| `trading.positions` | Execution Engine | Risk Engine | Position updates |
| `risk.alerts` | Risk Engine | Notification Service | Alerts |
| `analytics.trades` | Execution Engine | Analytics Engine | Closed trades |

### Redis Caching

| Key Pattern | TTL | Content |
|---|---|---|
| `tick:{symbol}` | 5s | Latest bid/ask |
| `candles:{symbol}:{tf}` | 60s | Last 500 candles |
| `session:current` | 60s | Active session info |
| `risk:state:{account_id}` | 30s | Risk metrics |
| `ai:signal:{symbol}` | 30s | Last AI signal |

### TimescaleDB Tables

- `ticks` (hypertable, symbol + timestamp partition)
- `candles_{M1,M5,M15,M30,H1,H4,D1}` (hypertables)
- `orders`, `positions`, `deals`
- `risk_states`, `risk_configs`, `risk_alerts`
- `ai_decisions`, `strategy_performance`

---

## 8. Security Model

### JWT Authentication

- **Algorithm**: RS256 in production (asymmetric RSA 2048-bit), HS256 in testing
- **Access token**: 15-minute expiry, contains `sub`, `role`, `permissions`
- **Refresh token**: 7-day expiry, single-use rotation
- **MFA**: TOTP (pyotp) with 8 backup codes

### RBAC Roles

| Role | Permissions |
|---|---|
| `viewer` | Read positions, orders, risk state, market data |
| `trader` | viewer + place/cancel orders, view AI signals |
| `admin` | trader + update risk config, reset circuit breaker, emergency close |
| `superadmin` | admin + user management, system configuration |

### Audit Log

Every API request is logged with: `user_id`, `action`, `endpoint`, `IP`, `timestamp`, `response_code`. Stored in PostgreSQL `audit_log` table, immutable (append-only trigger).

### Additional Controls

- **Rate Limiting**: slowapi middleware (100 req/min per IP, 10 login attempts/min)
- **CORS**: configurable whitelist via `CORS_ORIGINS` setting
- **TrustedHost**: enforced in production
- **Input Validation**: Pydantic v2 with strict type checking on all schemas
- **SQL Injection**: SQLAlchemy ORM with parameterised queries only

---

## 9. Deployment Architecture (K8s on AWS)

```
                        AWS Route 53 (DNS)
                               │
                    AWS ALB (Application Load Balancer)
                    ├── /api/v1/*  →  api-service
                    └── /ws/*      →  websocket-service

EKS Cluster
├── Namespace: forex-trading
│   ├── Deployment: api-service          (3 replicas, HPA 2-10)
│   ├── Deployment: websocket-service    (2 replicas)
│   ├── Deployment: risk-service         (2 replicas, StatefulSet)
│   ├── Deployment: ai-service           (2 replicas, GPU optional)
│   └── CronJob:    analytics-aggregator (every 1h)
│
├── Namespace: data
│   ├── StatefulSet: postgresql         (1 primary + 2 replicas)
│   ├── StatefulSet: redis-cluster      (6 nodes)
│   └── StatefulSet: kafka              (3 brokers + 3 zookeepers)
│
└── Namespace: observability
    ├── Deployment: prometheus
    ├── Deployment: grafana
    └── Deployment: jaeger

AWS Services Used:
  RDS PostgreSQL (TimescaleDB extension) – managed primary/replica
  ElastiCache Redis – managed cluster
  MSK (Kafka) – managed
  ECR – container registry
  S3 – ML model artifacts, backtest results
  Secrets Manager – JWT keys, broker credentials
  CloudWatch – log aggregation
```

### Deployment Pipeline

```
git push → GitHub Actions →
  1. pytest (unit + integration)
  2. ruff lint + mypy type check
  3. docker build + push to ECR
  4. kubectl apply (rolling update, max unavailable=1)
  5. smoke test against staging
  6. promote to production
```
