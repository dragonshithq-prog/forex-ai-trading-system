# Runbook: High Slippage Detected

> **Severity:** MEDIUM → HIGH (if sustained)  
> **Response Time:** < 10 minutes  
> **Owner:** On-Call Engineer / Risk Team  

## Symptoms

- Slippage alerts in monitoring dashboard
- Trade fill prices significantly different from expected
- P&L impact from slippage exceeds threshold
- Alert: `slippage_threshold_exceeded` in Grafana

## Thresholds

| Severity | Slippage (pips) | Action |
|----------|-----------------|--------|
| WARNING | > 2 pips | Investigate |
| HIGH | > 5 pips | Reduce position sizes |
| CRITICAL | > 10 pips | Halt trading, switch broker |

## Initial Diagnosis

```bash
# 1. Check current slippage metrics
curl -sf http://localhost:8000/api/v1/analytics/metrics | jq '.slippage'

# 2. Check recent trades with high slippage
curl -sf "http://localhost:8000/api/v1/trading/history?from_date=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)&limit=50" | \
    jq '.[] | select(.slippage_pips > 2) | {symbol, side, slippage_pips, fill_price, expected_price}'

# 3. Check market volatility
curl -sf "http://localhost:8000/api/v1/market/data?symbol=EURUSD" | jq '{bid, ask, spread}'
```

## Runbook Steps

### Step 1: Assess Market Conditions

```bash
# Check if high volatility event (news, economic data)
# Common high-slippage periods:
#   - 08:30 EST (US economic data)
#   - 10:00 EST (US economic data)
#   - 14:00 EST (FOMC, Fed speeches)
#   - Non-farm payroll Fridays
```

### Step 2: Adjust Risk Parameters

```bash
# 1. Reduce position sizes
curl -X PUT "http://localhost:8000/api/v1/risk/config" \
    -H "Content-Type: application/json" \
    -d '{"max_position_size_pct": 0.5}'

# 2. Increase slippage tolerance buffer
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.risk.engine import risk_engine
risk_engine.set_slippage_tolerance(slippage_pips=5.0)
print('Slippage tolerance adjusted to 5 pips')
"
```

### Step 3: Switch to LIMIT Orders

```bash
# Configure execution engine to prefer LIMIT over MARKET orders
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.execution.engine import execution_engine
execution_engine.set_order_type_preference('limit')
print('Execution engine set to prefer LIMIT orders')
"
```

### Step 4: If Slippage Persists > 10 pips

```bash
# Halt affected pairs
curl -X POST "http://localhost:8000/api/v1/risk/emergency-close-all" \
    -H "Content-Type: application/json" \
    -d '{"reason": "High slippage > 10 pips on EURUSD"}'
```

### Recovery

```bash
# 1. Reassess market conditions
# 2. Gradually increase position sizes
# 3. Switch back to MARKET orders when volatility normalizes
# 4. Reset risk parameters to defaults
```

## Prevention

- Use LIMIT orders during high-volatility news events
- Implement slippage limits per symbol
- Monitor spread widening in real-time
- Configure automated position size reduction based on ATR
