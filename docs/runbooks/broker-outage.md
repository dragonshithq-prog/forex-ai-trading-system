# Runbook: Broker API Outage

> **Severity:** HIGH  
> **Response Time:** < 5 minutes  
> **Owner:** On-Call Engineer  

## Symptoms

- API returns 502 Bad Gateway on trading endpoints
- `GET /health/ready` shows `broker: error`
- Position reconciliation failures
- Order placement timeouts or failures

## Initial Diagnosis

```bash
# Check broker health
curl -sf http://localhost:8000/health/ready | jq '.checks.broker'

# Check broker gateway connection status
curl -sf http://localhost:8000/api/v1/broker/connected | jq '.'

# Review broker plugin logs
kubectl logs -n forex-trading-production deployment/backend --tail=100 | grep -i "broker"

# Check outbox for pending events (if Kafka broker is separate)
psql -d forex_trading -c "SELECT count(*) FROM outbox_events WHERE status = 'pending';"
```

## Runbook Steps

### If It's a Transient Network Issue

```bash
# 1. Attempt to reconnect
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/connect"

# 2. Test connection
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/test"

# 3. Sync account data
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/sync"
```

### If Broker API Is Unreachable

```bash
# 1. Activate circuit breaker to prevent failed orders
curl -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/activate" \
    -H "Content-Type: application/json" \
    -d '{"reason": "Broker API unreachable"}'

# 2. Disable strategies that depend on this broker
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
strategy_repository.disable_by_broker('oanda')
print('OANDA strategies disabled')
"

# 3. Switch to backup broker if available
#    (This requires a configured backup broker account)
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.execution.services.broker_failover import BrokerFailover
failover = BrokerFailover()
failover.switch_to_backup('EURUSD')
print('Failed over to backup broker')
"
```

### Position Reconciliation

```bash
# 1. Check for discrepancies between local and broker state
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
from forex_trading.execution.services.reconciliation import ReconciliationService
svc = ReconciliationService()
discrepancies = await svc.find_discrepancies(account_id='...')
print(f'Found {len(discrepancies)} discrepancies')
"

# 2. If broker comes back, run full reconciliation
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
await svc.reconcile_all_positions(account_id='...')
"

# 3. If positions cannot be reconciled, flag for manual review
#    Write to #trading-alerts Slack channel
```

### Recovery

```bash
# 1. Verify broker is back online
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/test"

# 2. Reconnect
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/connect"

# 3. Sync all account data
curl -X POST "http://localhost:8000/api/v1/broker/accounts/{account_id}/sync"

# 4. Re-enable strategies
kubectl exec -n forex-trading-production deployment/backend -- \
    python -c "
strategy_repository.enable_by_broker('oanda')
"

# 5. Deactivate circuit breaker
curl -X POST "http://localhost:8000/api/v1/risk/circuit-breaker/reset" \
    -H "Content-Type: application/json"
```

## Escalation

If broker outage exceeds 15 minutes:

- Notify Broker Support (OANDA/MT5 provider)
- Consider switching to backup broker permanently for affected pairs
- File incident report
