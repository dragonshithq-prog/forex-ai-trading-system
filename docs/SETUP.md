# Setup Guide – Institutional Forex AI Trading Platform

## Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.12+ | pyenv recommended |
| Node.js | 20+ | npm 10+ |
| Docker + Docker Compose | 24+ | For local services |
| PostgreSQL | 15+ (TimescaleDB 2.x) | Or use Docker Compose |
| Redis | 7+ | Or use Docker Compose |
| Apache Kafka | 3.5+ | Or use Docker Compose |
| Git | 2.x | |

---

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/forex-trading-system.git
cd forex-trading-system
```

---

## 2. Backend Setup

### 2.1 Create Virtual Environment

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2.2 Install Dependencies

```bash
# Core + dev dependencies
pip install -e ".[dev]"

# Optional: ML extras (PyTorch, SHAP)
pip install -e ".[ml]"

# Optional: Broker connectivity (OANDA, MT5)
pip install -e ".[broker]"
```

### 2.3 Environment Configuration

Copy and edit the example environment file:

```bash
cp ../.env.example .env
```

Edit `.env`:

```dotenv
# Application
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=<generate-with: python -c "import secrets; print(secrets.token_hex(32))">

# Database
DATABASE_URL=postgresql+asyncpg://forex:forex@localhost:5432/forex_trading

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ (optional – used for Kafka-less dev)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# JWT (for development, HS256 is fine)
JWT_SECRET_KEY=<generate-with: python -c "import secrets; print(secrets.token_hex(32))">
JWT_ALGORITHM=HS256

# Risk Limits
MAX_POSITION_SIZE_PCT=2.0
MAX_TOTAL_EXPOSURE_PCT=20.0
MAX_DRAWDOWN_DAILY_PCT=3.0
MAX_DRAWDOWN_TOTAL_PCT=15.0
MAX_POSITIONS=10

# Broker (leave empty to use paper trading only)
OANDA_API_KEY=
OANDA_ACCOUNT_ID=
OANDA_ENVIRONMENT=practice
```

> **Production Note**: Generate an RSA-2048 key pair for JWT:
> ```bash
> openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:2048
> openssl rsa -pubout -in private.pem -out public.pem
> # Set JWT_SECRET_KEY = contents of private.pem and JWT_ALGORITHM=RS256
> ```

### 2.4 Database Setup

Start PostgreSQL (or use Docker Compose – see §4):

```bash
# Create database and user
psql -U postgres -c "CREATE USER forex WITH PASSWORD 'forex';"
psql -U postgres -c "CREATE DATABASE forex_trading OWNER forex;"

# Run Alembic migrations
cd backend
alembic upgrade head
```

### 2.5 Run the Backend

```bash
# Development mode with hot-reload
uvicorn forex_trading.main:app --reload --host 0.0.0.0 --port 8000

# Or via the project script
python -m forex_trading.main
```

API will be available at: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

## 3. Frontend Setup

```bash
cd frontend
npm install
```

Create `.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

Start the dev server:

```bash
npm run dev
```

Frontend will be at: `http://localhost:3000`

---

## 4. Docker Compose (All Services)

This starts PostgreSQL, Redis, Kafka, Zookeeper, and the backend API in containers:

```bash
# From the project root
docker compose up -d

# Check all services are healthy
docker compose ps

# View logs
docker compose logs -f api
```

### Available Services

| Service | URL / Port |
|---|---|
| API | http://localhost:8000 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Kafka | localhost:9092 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

### Stop Services

```bash
docker compose down          # stop containers
docker compose down -v       # stop and remove volumes (data loss!)
```

---

## 5. MT4/MT5 Bridge EA Setup

The MetaTrader bridge uses a TCP socket Expert Advisor (EA) to relay orders.

### Install the EA

1. Copy `infrastructure/mt4/ForexAI_Bridge.mq4` to your MT4/MT5 `Experts/` folder.
2. In MetaTrader: Tools → Options → Expert Advisors → Allow automated trading ✓
3. Attach the EA to any chart (it operates on all symbols).

### Configure the EA

Set the EA parameters:
- `SERVER_HOST`: IP of the backend server (default: `127.0.0.1`)
- `SERVER_PORT`: gRPC port (default: `50051`)
- `HEARTBEAT_INTERVAL`: seconds between keepalives (default: `5`)

### Backend MT4/MT5 Settings

```dotenv
MT4_HOST=127.0.0.1
MT4_PORT=50051
MT5_HOST=127.0.0.1
MT5_PORT=50052
```

---

## 6. OANDA Paper Trading Setup

### Get an OANDA Practice Account

1. Sign up at https://www.oanda.com/register/
2. Select "Practice Account"
3. Go to My Account → Manage API Access → Generate Token

### Configure

```dotenv
OANDA_API_KEY=<your-practice-api-key>
OANDA_ACCOUNT_ID=<your-account-id>  # e.g., 001-001-12345678-001
OANDA_ENVIRONMENT=practice
```

### Test the Connection

```bash
python -c "
from forex_trading.broker.oanda import OANDAPlugin
import asyncio

async def test():
    plugin = OANDAPlugin()
    await plugin.connect()
    info = await plugin.get_account_info()
    print('Balance:', info.balance)
    await plugin.disconnect()

asyncio.run(test())
"
```

---

## 7. Running Tests

### Unit Tests (no external services required)

```bash
cd backend
pytest tests/unit/ -q
```

### Integration Tests (mocked DB/services)

```bash
pytest tests/integration/ -q
```

### Security Tests

```bash
pytest tests/security/ -q
```

### E2E Tests (full pipeline, mocked broker)

```bash
pytest tests/e2e/ -q
```

### Load / Performance Tests (slow)

```bash
pytest tests/load/ -q -m slow
```

### All Tests

```bash
pytest tests/ --ignore=tests/unit/test_core_domain.py -q
```

### Coverage Report

```bash
pytest tests/ --ignore=tests/unit/test_core_domain.py \
  --cov=src/forex_trading \
  --cov-report=html \
  --cov-report=term-missing \
  -q

# Open coverage report
start htmlcov/index.html      # Windows
open htmlcov/index.html        # macOS
```

---

## 8. Grafana Dashboard

After running `docker compose up -d`, access Grafana at `http://localhost:3001`.

- **Username**: `admin`
- **Password**: `admin` (change on first login)

### Import Pre-built Dashboards

1. In Grafana: + → Import
2. Upload files from `infrastructure/grafana/dashboards/`:
   - `forex_overview.json` – P&L, positions, win rate
   - `ai_agents.json` – Agent consensus, signal history
   - `risk_engine.json` – Drawdown, circuit breaker status
   - `system_health.json` – API latency, error rates

### Key Metrics

| Panel | Description |
|---|---|
| Daily P&L | Realised + unrealised profit/loss |
| Win Rate (7d) | % of profitable trades in last 7 days |
| Active Positions | Current open positions by symbol |
| AI Consensus | Last signal direction and confidence |
| Drawdown | Current vs. daily/max drawdown limits |
| Circuit Breaker | Active/inactive status + reason |
| API P99 Latency | 99th percentile response time |

---

## 9. Production Checklist

Before deploying to production:

- [ ] Set `ENVIRONMENT=production` and `DEBUG=false`
- [ ] Generate production JWT RSA-2048 key pair
- [ ] Store all secrets in AWS Secrets Manager (not `.env`)
- [ ] Set `CORS_ORIGINS` to your production domain only
- [ ] Enable `TrustedHostMiddleware` with your domain
- [ ] Run `alembic upgrade head` against the production DB
- [ ] Set up `prometheus` scrape targets
- [ ] Configure Grafana alerting for:
  - Drawdown > 2% (warning) / > 2.5% (critical)
  - Circuit breaker activated
  - API error rate > 1%
- [ ] Test broker connectivity from the production network
- [ ] Perform a dry-run paper trade before enabling live trading
- [ ] Review and confirm all `RiskLimits` values with the trading team
