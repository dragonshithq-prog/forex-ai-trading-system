# Forex AI Trading System

[![CI Pipeline](https://github.com/your-org/forex-trading-system/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/forex-trading-system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Institutional-grade, autonomous AI Forex trading ecosystem built with Clean Architecture, DDD, and Event-Driven design.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INTERACTION LAYER                        │
│              (Dashboard, Analytics, Alerts, API)                 │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────┐
│                      ORCHESTRATION LAYER                         │
│            (Event Bus, Workflow Engine, Session Manager)         │
└──┬──────────┬──────────┬───────────┬──────────┬────────────────┘
   │          │          │           │          │
   ▼          ▼          ▼           ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Market│ │  AI    │ │Strategy│ │  Risk  │ │Broker  │
│ Data │ │Agents  │ │ Engine │ │ Engine │ │Gateway │
└──────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | Python 3.12, FastAPI, gRPC |
| Database | PostgreSQL, TimescaleDB, Redis |
| Message Bus | RabbitMQ, Kafka |
| AI/ML | PyTorch, Scikit-learn, SHAP |
| Infrastructure | Docker, Kubernetes, AWS, Terraform |
| Monitoring | Prometheus, Grafana, ELK Stack |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 16+ (or use Docker)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/forex-trading-system.git
   cd forex-trading-system
   ```

2. **Start infrastructure services**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

3. **Setup backend**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

4. **Setup frontend**
   ```bash
   cd frontend
   npm install
   ```

5. **Run development servers**
   ```bash
   # Backend (Terminal 1)
   cd backend
   uvicorn forex_trading.main:app --reload --port 8000

   # Frontend (Terminal 2)
   cd frontend
   npm run dev
   ```

### Docker Development

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up

# View logs
docker-compose -f docker/docker-compose.yml logs -f backend

# Stop all services
docker-compose -f docker/docker-compose.yml down
```

## Project Structure

```
forex-trading-system/
├── backend/                    # Python Backend (FastAPI)
│   ├── src/forex_trading/
│   │   ├── core/              # Domain entities, events, security
│   │   ├── market_data/       # Market data service
│   │   ├── ai/                # AI orchestration & agents
│   │   ├── strategy/          # Strategy engine
│   │   ├── risk/              # Risk management (authoritative)
│   │   ├── execution/         # Order execution
│   │   ├── broker/            # Broker gateway plugins
│   │   ├── analytics/         # Analytics & reporting
│   │   ├── notifications/     # Notification service
│   │   └── shared/            # Shared infrastructure
│   └── tests/
├── frontend/                   # Next.js Frontend
│   ├── src/
│   │   ├── app/               # App Router pages
│   │   ├── components/        # React components
│   │   └── lib/               # Utilities & API client
│   └── public/
├── ml/                         # ML Models & Training
├── infrastructure/             # Terraform IaC
├── docs/                       # Documentation
├── docker/                     # Docker configuration
└── .github/                    # CI/CD workflows
```

## Key Features

- **Multi-Broker Support**: MT4, MT5, OANDA, FXCM, cTrader, Interactive Brokers
- **AI-Powered Analysis**: Multiple specialized agents with consensus mechanism
- **Smart Money Concepts**: SMC, Order Blocks, Fair Value Gaps, Liquidity Zones
- **Institutional Risk Management**: Authoritative risk engine with circuit breakers
- **Explainable AI**: Full audit trail for every trading decision
- **Real-time Dashboard**: Live P&L, positions, and analytics
- **Backtesting Engine**: Historical strategy validation

## API Documentation

Once running, access the API docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

```bash
# Run all tests
cd backend
pytest

# Run with coverage
pytest --cov=src/forex_trading --cov-report=html

# Run specific test category
pytest -m unit
pytest -m integration
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.
