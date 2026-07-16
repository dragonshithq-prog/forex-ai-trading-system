# Runbook: Risk Circuit Breaker Tripped

> **Severity:** HIGH  
> **Response Time:** < 5 minutes  
> **Owner:** On-Call Engineer / Risk Team  

## Symptoms

- Alert: `circuit_breaker_activated` in Slack/Email
- All trading API calls return 403 with circuit breaker violation
- `GET /health/ready` shows `risk_engine: circuit_breaker_active`
- No new orders can be placed or positions opened

## Causes

| Cause | Detection | Typical Cooldown |
|-------|-----------|-----------------|
| Max consecutive losses exceeded | `consecutive_losses > threshold` | 60 min |
| Daily drawdown limit exceeded | `daily_drawdown > 3%` | Next day |
| Weekly drawdown limit exceeded | `weekly_drawdown > 5%` | Next week |
| High slippage detected | `slippage_pips > threshold` | 30 min |
| Broker outage | `broker_health = error` | Until broker recovers |
| Manual trigger | Operator-initiated | Variable |

## Initial Diagnosis

```bash
# 1. Get current circuit breaker state
curl -sf http://localhost:8000/api/v1/risk/circuit-breaker/status | jq '.'

# 2. Get recent risk alerts
curl -sf "http://localhost:8000/api/v1/risk/alerts?level=critical&limit=10" | jq '.'

# 3. Check recent trading activity
curl -sf "http://localhost:8000/api/v1/trading/history?limit=20" | jq '.[] | {symbol, side, pnl, status}'

# 4. Check current drawdown
curl -sf "http://localhost:8000/api/v1/risk/state" | jq '{current_drawdown_pct, circuit_breaker_active, circuit_breaker_reason}'
```

## Runbook Steps

### Step 1: Determine Cause

```bash
# Check circuit breaker reason
REASON=$(curl -sf http://localhost:8000/api/v1/risk/circuit-breaker/status | jq -r '.reason')
echo "Circuit breaker reason: ${REASON}"

# Check consecutive losses
LOSSES=$(curl -sf http://localhost:8000/api/v1/risk/state | jq '.consecutive_losses')
echo "Consecutive losses: ${LOSSES}"
```

### Step 2: Assess Severity

| Condition | Action | Timeline |
|-----------|--------|----------|
| Single broker account | Investigate that account | < 15 min |
| All accounts (global) | System-wide investigation | < 5 min |
| Manual trigger | Contact trigger author | < 10 min |
| Unknown cause | Assume security incident | Immediate |

### Step 3: Investigate Root Cause

```bash
# For consecutive losses:
#   - Review strategy performance
#   - Check if market regime changed
#   - Review AI agent agreement levels

# For drawdown limit:
#   - Check if a single large trade caused it
#   - Verify risk limit calculations
#   - Check for position sizing errors

# For high slippage:
#   - Check broker connectivity
#   - Verify market data feed quality
#   - Review order execution latency
```

### Step 4: Manual Reset (if appropriate)

```bash
# ONLY reset if root cause is understood and resolved
curl -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/reset" \
    -H "Content-Type: application/json" \
    -d '{"broker_account_id": "global"}'

# Verify reset
curl -sf http://localhost:8000/api/v1/risk/circuit-breaker/status | jq '.is_active'
# Expected: false
```

### Step 5: Resume Trading Gradually

```bash
# 1. Start with reduced position sizes
curl -X PUT "http://localhost:8000/api/v1/risk/config" \
    -H "Content-Type: application/json" \
    -d '{"max_position_size_pct": 0.5}'  # 50% of normal

# 2. Monitor first few trades
curl -sf "http://localhost:8000/api/v1/trading/history?limit=5" | jq '.'

# 3. Gradually increase to normal position sizes
```

### Step 6: If Circuit Breaker Re-trips

```bash
# This indicates systemic issues
# 1. HALT ALL TRADING
# 2. Follow trading-halt.md runbook
# 3. Escalate to Risk Team Lead and Trading Supervisor
# 4. Do NOT reset until root cause is fully resolved
```

## Prevention

- Review and adjust risk limits quarterly
- Implement tiered circuit breakers (warning → soft → hard)
- Improve AI signal quality monitoring
- Regular chaos engineering testing
