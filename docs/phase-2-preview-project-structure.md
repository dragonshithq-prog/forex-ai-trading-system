# Phase 2 Preview: Project Structure
## Proposed Monorepo Layout

```
forex-ai-trading-system/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # Main CI pipeline
│   │   ├── cd.yml                    # Deployment pipeline
│   │   ├── security-scan.yml         # Dependabot + Trivy
│   │   └── release.yml               # Release automation
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── pull_request_template.md
│
├── backend/                          # Python Backend (FastAPI)
│   ├── pyproject.toml                # Python project config
│   ├── alembic.ini                   # Database migrations config
│   ├── alembic/
│   │   ├── versions/                 # Migration scripts
│   │   └── env.py
│   │
│   ├── src/
│   │   └── forex_trading/
│   │       ├── __init__.py
│   │       ├── main.py               # FastAPI application entry
│   │       ├── config.py             # Configuration management
│   │       ├── dependencies.py       # Dependency injection
│   │       │
│   │       ├── core/                 # Shared kernel
│   │       │   ├── domain/           # Base domain entities
│   │       │   ├── events/           # Event bus interfaces
│   │       │   ├── exceptions/       # Custom exceptions
│   │       │   ├── security/         # Auth, JWT, RBAC
│   │       │   └── utils/            # Shared utilities
│   │       │
│   │       ├── market_data/          # Market Data Service
│   │       │   ├── api/              # REST endpoints
│   │       │   ├── domain/           # Market entities
│   │       │   ├── services/         # Business logic
│   │       │   ├── infrastructure/   # External integrations
│   │       │   └── tests/
│   │       │
│   │       ├── ai/                   # AI Orchestration Service
│   │       │   ├── api/
│   │       │   ├── agents/           # Agent implementations
│   │       │   │   ├── base.py       # BaseAgent interface
│   │       │   │   ├── structure.py  # Market Structure Agent
│   │       │   │   ├── trend.py      # Trend Agent
│   │       │   │   ├── momentum.py   # Momentum Agent
│   │       │   │   ├── liquidity.py  # Liquidity Agent
│   │       │   │   ├── sentiment.py  # Sentiment Agent
│   │       │   │   ├── volatility.py # Volatility Agent
│   │       │   │   └── correlation.py# Correlation Agent
│   │       │   ├── consensus/        # Consensus engine
│   │       │   ├── xai/              # Explainable AI
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       ├── strategy/             # Strategy Engine
│   │       │   ├── api/
│   │       │   ├── strategies/       # Strategy implementations
│   │       │   │   ├── base.py
│   │       │   │   ├── trend_following.py
│   │       │   │   ├── mean_reversion.py
│   │       │   │   ├── scalping.py
│   │       │   │   ├── breakout.py
│   │       │   │   └── grid.py
│   │       │   ├── registry/         # Strategy registry
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       ├── risk/                 # Risk Engine (AUTHORITATIVE)
│   │       │   ├── api/
│   │       │   ├── domain/
│   │       │   │   ├── limits.py     # Risk limits
│   │       │   │   ├── exposure.py   # Exposure management
│   │       │   │   ├── drawdown.py   # Drawdown tracking
│   │       │   │   └── circuit_breaker.py
│   │       │   ├── services/
│   │       │   ├── middleware/        # Override middleware
│   │       │   └── tests/
│   │       │
│   │       ├── execution/            # Execution Engine
│   │       │   ├── api/
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       ├── broker/               # Broker Gateway
│   │       │   ├── api/
│   │       │   ├── plugins/          # Broker plugins
│   │       │   │   ├── base.py       # BrokerPlugin interface
│   │       │   │   ├── oanda.py
│   │       │   │   ├── mt4.py
│   │       │   │   ├── mt5.py
│   │       │   │   ├── fxcm.py
│   │       │   │   ├── cTrader.py
│   │       │   │   └── ibkr.py
│   │       │   ├── discovery/        # Auto-discovery
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       ├── analytics/            # Analytics Service
│   │       │   ├── api/
│   │       │   ├── backtesting/      # Backtesting engine
│   │       │   ├── optimization/     # Parameter optimization
│   │       │   ├── reporting/        # Report generation
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       ├── notifications/        # Notification Service
│   │       │   ├── channels/
│   │       │   │   ├── email.py
│   │       │   │   ├── slack.py
│   │       │   │   ├── telegram.py
│   │       │   │   └── webhook.py
│   │       │   ├── templates/
│   │       │   ├── domain/
│   │       │   ├── services/
│   │       │   └── tests/
│   │       │
│   │       └── shared/               # Shared infrastructure
│   │           ├── database/         # DB connections, sessions
│   │           ├── cache/            # Redis client
│   │           ├── events/           # Event bus implementation
│   │           ├── messaging/        # RabbitMQ/Kafka client
│   │           └── monitoring/       # Metrics, tracing
│   │
│   ├── tests/                        # Integration tests
│   └── benchmarks/                   # Performance benchmarks
│
├── frontend/                         # Next.js Frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   │
│   ├── src/
│   │   ├── app/                      # App Router pages
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx              # Dashboard
│   │   │   ├── trading/
│   │   │   │   ├── page.tsx          # Trading view
│   │   │   │   └── [symbol]/page.tsx
│   │   │   ├── analytics/
│   │   │   │   ├── page.tsx          # Analytics dashboard
│   │   │   │   └── backtest/page.tsx
│   │   │   ├── risk/
│   │   │   │   └── page.tsx          # Risk monitor
│   │   │   ├── settings/
│   │   │   │   └── page.tsx
│   │   │   └── auth/
│   │   │       └── page.tsx
│   │   │
│   │   ├── components/
│   │   │   ├── ui/                   # Base UI components
│   │   │   ├── charts/               # TradingView integration
│   │   │   │   ├── CandlestickChart.tsx
│   │   │   │   ├── DepthChart.tsx
│   │   │   │   └── PnLChart.tsx
│   │   │   ├── trading/              # Trading components
│   │   │   ├── risk/                 # Risk visualization
│   │   │   └── layout/               # Layout components
│   │   │
│   │   ├── hooks/                    # Custom React hooks
│   │   ├── lib/                      # Utilities, API client
│   │   ├── stores/                   # State management
│   │   └── types/                    # TypeScript types
│   │
│   └── public/                       # Static assets
│
├── ml/                               # ML Models & Training
│   ├── models/                       # Model definitions
│   ├── training/                     # Training scripts
│   ├── notebooks/                    # Jupyter notebooks
│   ├── data/                         # Training data
│   └── artifacts/                    # Trained models
│
├── infrastructure/                   # Terraform IaC
│   ├── modules/
│   │   ├── vpc/
│   │   ├── eks/
│   │   ├── rds/
│   │   ├── elasticache/
│   │   └── s3/
│   ├── environments/
│   │   ├── dev/
│   │   ├── staging/
│   │   └── production/
│   └── main.tf
│
├── docs/                             # Documentation
│   ├── architecture/
│   ├── api/
│   ├── deployment/
│   └── runbooks/
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── docker-compose.yml            # Local development
│   └── docker-compose.prod.yml       # Production-like
│
├── scripts/                          # Utility scripts
│   ├── setup.sh                      # Initial setup
│   ├── seed_data.py                  # Historical data loader
│   └── generate_docs.sh
│
├── .env.example                      # Environment template
├── .gitignore
├── .editorconfig
├── .pre-commit-config.yaml
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

## Clean Architecture Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY RULE                                 │
│                                                                   │
│  External │ Infrastructure │ Application │ Domain                 │
│  Frameworks│               │             │                        │
│     ◄──────┤◄──────────────┤◄────────────┤                        │
│            │               │             │                        │
│  FastAPI   │  DB Clients   │  Use Cases  │  Entities              │
│  PyTorch   │  Redis Client │  Services   │  Value Objects         │
│  SQLAlchemy│  MQ Clients   │  DTOs       │  Domain Events         │
│            │  API Clients  │  Interfaces │  Business Rules        │
│                                                                   │
│  Dependencies point INWARD toward the Domain layer.              │
│  Domain layer has NO dependencies on external frameworks.        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Development Phases Progression

| Phase | Deliverable | Dependencies |
|-------|-------------|--------------|
| 1 | Architecture & Tech Spec | None |
| 2 | Project Structure & Tooling | Phase 1 ✅ |
| 3 | Database Schema & Migrations | Phase 2 |
| 4 | Backend Services (Core) | Phase 3 |
| 5 | Broker Integration | Phase 4 |
| 6 | Market Data Engine | Phase 4 |
| 7 | AI Framework | Phase 4, 6 |
| 8 | Strategy Engine | Phase 4, 7 |
| 9 | Risk Engine | Phase 4 |
| 10 | Dashboard & UI | Phase 4 |
| 11 | Analytics & Reporting | Phase 4, 8 |
| 12 | Notifications | Phase 4 |
| 13 | Backtesting | Phase 8, 11 |
| 14 | Paper Trading | Phase 5, 8, 9 |
| 15 | Production Deployment | All previous |
| 16 | QA & Stress Testing | Phase 15 |
| 17 | Documentation | Phase 16 |
