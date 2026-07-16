# Runbook: Market Data Latency Exceeded

> **Severity:** MEDIUM → HIGH (if sustained > 30 seconds)  
> **Response Time:** < 5 minutes  
> **Owner:** On-Call Engineer  

## Symptoms

- Alert: `market_data_lag > 5 seconds` in Grafana
- Tick timestamps are significantly behind real-time
- AI agents analyzing stale data
- Trading decisions based on outdated prices
- `GET /health/ready` shows `market_data: degraded`

## Thresholds

| Severity | Latency | Action |
|----------|---------|--------|
| WARNING | > 2 seconds | Monitor |
| HIGH | > 5 seconds | Investigate |
| CRITICAL | > 30 seconds | Halt trading on affected pairs |

## Initial Diagnosis

```bash
# 1. Check market data health
curl -sf http://localhost:8000/health/ready | jq '.checks.market_data'

# 2. Check current data freshness for active symbols
curl -sf "http://localhost:8000/api/v1/market/data?symbol=EURUSD" | jq '{symbol, bid, ask, timestamp}'

# 3. Compare system time to data timestamp
echo "System time: $(date -u +%s)"
curl -sf "http://localhost:8000/api/v1/market/data?symbol=EURUSD" | jq '.timestamp'

# 4. Check market data provider status
kubectl logs -n forex-trading-production deployment/backend --tail=100 | grep -i "market\|tick\|quote" | tail -20
```

## Runbook Steps

### Step 1: Identify Source of Lag

```bash
# Network latency to provider
kubectl exec -n forex-trading-production deployment/backend -- \
    ping -c 5 data.provider.com 2>/dev/null

# Data pipeline congestion
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.market_data.services.market_data_service import MarketDataService
svc = MarketDataService()
lag = svc.get_data_freshness()
print(f'Data lag: {lag}')
"
```

### Step 2: If Network-Related

```bash
# 1. Check provider status page
# 2. Switch to backup data provider
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.market_data.services.provider_failover import ProviderFailover
failover = ProviderFailover()
failover.switch_to_backup()
print('Switched to backup data provider')
"

# 3. Update data source routing
```

### Step 3: If Processing-Related

```bash
# 1. Check consumer lag
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from kafka import KafkaConsumer
consumer = KafkaConsumer('market.ticks', bootstrap_servers='localhost:9092')
print(f'Partition lag: {consumer.metrics()}')  
"

# 2. If backlog exists, reset consumer to latest
kafka-consumer-groups \
    --bootstrap-server localhost:9092 \
    --group forex-trading-market-data \
    --topic market.ticks \
    --reset-offsets --to-latest --execute
```

### Step 4: If Data Feed Is Unrecoverable

```bash
# 1. Halt trading on affected symbols
curl -X POST "http://localhost:8000/api/v1/risk/emergency-close-all" \
    -H "Content-Type: application/json" \
    -d '{"reason": "Market data feed failure on EURUSD"}'

# 2. Disable strategies using this data
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.shared.database.crud_strategy import strategy_repository
strategy_repository.disable_by_symbol('EURUSD')
print('EURUSD strategies disabled')
"
```

### Step 5: Recovery

```bash
# 1. Once data feed is restored, verify freshness
curl -sf "http://localhost:8000/api/v1/market/data?symbol=EURUSD" | jq '.timestamp'

# 2. Re-enable strategies
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
strategy_repository.enable_by_symbol('EURUSD')
"

# 3. Verify AI models are using current data
```

## Prevention

- Dual data provider architecture (primary + backup)
- Data freshness health checks every 5 seconds
- Automatic failover on latency > threshold
- Rate-limited data ingestion to prevent backlog
- Alert on any tick timestamp older than 5 seconds
