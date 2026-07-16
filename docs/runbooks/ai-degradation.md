# Runbook: AI Signal Quality Degradation

> **Severity:** MEDIUM  
> **Response Time:** < 15 minutes  
> **Owner:** AI/ML Team / On-Call Engineer  

## Symptoms

- Alert: `ai_signal_quality_below_threshold`
- AI agent agreement levels drop below 60%
- AI decision confidence scores are low
- Increasing number of AI decisions being overridden by risk engine
- AI agent error rates increasing

## Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Agent Agreement | < 60% | < 40% | Investigate agents |
| Signal Confidence | < 0.5 | < 0.3 | Reduce position sizes |
| Prediction Error | > 5% | > 10% | Retrain models |
| Agent Health | < 95% | < 80% | Restart agents |

## Initial Diagnosis

```bash
# 1. Check AI system health
curl -sf http://localhost:8000/api/v1/strategy/decisions?limit=20 | \
    jq '.[] | {symbol, direction, confidence, agent_agreement_pct, status}'

# 2. Check recent AI decisions
curl -sf "http://localhost:8000/api/v1/strategy/decisions?rejected_only=true&limit=20" | \
    jq '.[] | {symbol, confidence, rejection_reason}'

# 3. Check agent performance
curl -sf "http://localhost:8000/api/v1/strategy/agents" | \
    jq '.[] | {agent_type, win_rate, sharpe_ratio, total_trades, accuracy}'
```

## Runbook Steps

### Step 1: Determine Degradation Pattern

```bash
# Check which agents are underperforming
curl -sf "http://localhost:8000/api/v1/strategy/agents?agent_type=technical" | jq '.'
curl -sf "http://localhost:8000/api/v1/strategy/agents?agent_type=fundamental" | jq '.'
curl -sf "http://localhost:8000/api/v1/strategy/agents?agent_type=sentiment" | jq '.'

# Check if degradation is symbol-specific
curl -sf "http://localhost:8000/api/v1/strategy/agents?symbol=EURUSD" | jq '.'
curl -sf "http://localhost:8000/api/v1/strategy/agents?symbol=GBPUSD" | jq '.'
```

| Pattern | Likely Cause | Action |
|---------|-------------|--------|
| All agents degraded | Data quality issue | Check market data freshness |
| Single agent degraded | Agent-specific issue | Restart agent, check model |
| Single symbol degraded | Symbol-specific issue | Check symbol data, market regime |
| Degradation over time | Model drift | Retrain model |

### Step 2: Apply Mitigation

```bash
# 1. Reduce position sizes (lower confidence = lower exposure)
curl -X PUT "http://localhost:8000/api/v1/risk/config" \
    -H "Content-Type: application/json" \
    -d '{
        "max_position_size_pct": 0.5,
        "max_total_exposure_pct": 10.0
    }'

# 2. Increase minimum agreement threshold
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.ai.orchestrator import AIOrchestrator
orch = AIOrchestrator()
orch.set_min_agreement_threshold(0.75)  # Require 75% agreement
print('Min agreement threshold raised to 75%')
"

# 3. Disable the most degraded agents
curl -sf "http://localhost:8000/api/v1/strategy/agents" | \
    jq '.[] | select(.accuracy < 0.4) | .agent_type'
# Disable identified agents
```

### Step 3: Restart AI Services

```bash
# Restart AI agent workers
kubectl rollout restart deployment/ai-worker -n forex-trading-production

# Clear AI cache (stale predictions)
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.shared.cache import cache_manager
cache_manager.clear_pattern('ai:*')
print('AI cache cleared')
"
```

### Step 4: If Degradation Persists

```bash
# 1. Switch to conservative trading mode
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.execution.engine import execution_engine
execution_engine.set_trading_mode('conservative')
print('Switched to conservative trading mode')
"

# 2. Reduce trading frequency
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.execution.services.auto_trader import auto_trader
auto_trader.set_poll_interval(3600)  # Check every hour instead of every 5 min
"

# 3. Notify AI/ML team for model investigation
```

### Recovery

```bash
# 1. Verify AI system health restored
curl -sf http://localhost:8000/health/ready | jq '.checks.ai_orchestrator'

# 2. Gradually restore settings
curl -X PUT "http://localhost:8000/api/v1/risk/config" \
    -H "Content-Type: application/json" \
    -d '{"max_position_size_pct": 2.0}'

# 3. Reset agreement threshold
kubectl exec deployment/backend -n forex-trading-production -- \
    python -c "orch.set_min_agreement_threshold(0.6)"

# 4. Re-enable agents
# 5. Restore normal trading mode
```

## Prevention

- Monthly model retraining pipeline
- Automated agent performance tracking
- A/B testing framework for new models
- Data quality monitoring dashboard
- Regular feature importance analysis
- Concept drift detection on production data
