# Runbook: Emergency Trading Halt

> **Severity:** CRITICAL  
> **Response Time:** Immediate (< 1 minute)  
> **Owner:** On-Call Engineer / Risk Team  

## Objective

Immediately halt ALL trading activity, close all open positions, and disable all strategies in response to anomalous market conditions, system malfunction, or security incident.

## Triggers

- Security breach detected (unauthorized access, API key compromise)
- Catastrophic system failure (multiple services down simultaneously)
- Erroneous trading behavior (runaway orders, incorrect pricing)
- Regulatory hold or compliance directive
- Manual decision by Risk Officer or Trading Supervisor

## Pre-flight Check (15 seconds)

```bash
# Check current trading state
curl -sf http://localhost:8000/api/v1/risk/state | jq '.'

# Check if circuit breaker already active
curl -sf http://localhost:8000/api/v1/risk/circuit-breaker/status | jq '.'

# Count open positions
curl -sf http://localhost:8000/api/v1/trading/positions | jq 'length'
```

## Emergency Halt Procedure

### Step 1: Disable All Strategies

```bash
# Disable all active strategies
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.shared.database.crud_strategy import strategy_repository
# Bulk disable all strategies
strategy_repository.bulk_update_status('active', 'halted')
print('All strategies halted')
"
```

### Step 2: Activate Risk Circuit Breaker

```bash
# API call to activate circuit breaker
curl -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/activate" \
    -H "Content-Type: application/json" \
    -d '{
        "reason": "Emergency halt triggered by on-call engineer",
        "cooldown_minutes": 1440
    }'
```

### Step 3: Emergency Close All Positions

```bash
# Close all positions across all broker accounts
curl -X POST "http://localhost:8000/api/v1/risk/emergency-close-all" \
    -H "Content-Type: application/json" \
    -d '{
        "reason": "Emergency trading halt - system directive"
    }'
```

### Step 4: Disable Order Placement

```bash
# Block order creation at the API level
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.risk.engine import risk_engine
risk_engine.disable_order_placement()
print('Order placement disabled')
"
```

### Step 5: Scale Down Autotrader

```bash
# Stop auto-trading cron jobs and background workers
kubectl scale deployment celery-worker -n forex-trading-production --replicas=0
```

### Step 6: Notify Stakeholders

```bash
# Send Slack alert
curl -X POST "${SLACK_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d '{
        "channel": "#incidents",
        "text": ":rotating_light: *EMERGENCY TRADING HALT*\nTriggered by: On-Call Engineer\nTime: $(date -u +%FT%TZ)\nAction: All positions closed, strategies halted"
    }'
```

## Verification

```bash
# Verify no open positions
curl -sf http://localhost:8000/api/v1/trading/positions | jq 'length'
# Expected: 0

# Verify circuit breaker state
curl -sf http://localhost:8000/api/v1/risk/circuit-breaker/status | jq '.is_active'
# Expected: true

# Verify order placement blocked
curl -sf -X POST http://localhost:8000/api/v1/trading/orders \
    -H "Content-Type: application/json" \
    -d '{"symbol":"EURUSD","side":"buy","quantity":0.01}'
# Expected: 403 or circuit breaker violation
```

## Resume Trading

Only authorized by Risk Officer + Trading Supervisor:

```bash
# 1. Investigate and resolve root cause
# 2. Verify system integrity
# 3. Run validation checks:
#    - ./scripts/validate-config.sh
#    - ./scripts/smoke-test.sh

# 4. Deactivate circuit breaker
curl -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/reset" \
    -H "Content-Type: application/json" \
    -d '{"broker_account_id": "global"}'

# 5. Enable order placement
kubectl exec deployment/backend -n forex-trading-production -- \
    python -c "risk_engine.enable_order_placement()"

# 6. Resume strategies
kubectl exec deployment/backend -n forex-trading-production -- \
    python -c "strategy_repository.bulk_update_status('halted', 'active')"

# 7. Scale up worker
kubectl scale deployment celery-worker -n forex-trading-production --replicas=3

# 8. Monitor for 30 minutes before leaving
```

## Post-Incident

- File incident report within 1 hour
- Root cause analysis within 24 hours
- Update runbook with lessons learned
- Review and adjust trading halt triggers
