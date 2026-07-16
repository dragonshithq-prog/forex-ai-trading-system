# API Reference — Forex AI Trading System

> **Base URL**: `http://localhost:8000/api/v1`  
> **OpenAPI**: http://localhost:8000/docs  
> **Authentication**: JWT Bearer Token or API Key  
> **Version**: 0.1.0

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Auth Endpoints](#2-auth-endpoints)
3. [Trading Endpoints](#3-trading-endpoints)
4. [Risk Management Endpoints](#4-risk-management-endpoints)
5. [Broker Endpoints](#5-broker-endpoints)
6. [Market Data Endpoints](#6-market-data-endpoints)
7. [Strategy Endpoints](#7-strategy-endpoints)
8. [AI Endpoints](#8-ai-endpoints)
9. [Account Endpoints](#9-account-endpoints)
10. [Analytics Endpoints](#10-analytics-endpoints)
11. [Monitoring Endpoints](#11-monitoring-endpoints)
12. [WebSocket Protocol](#12-websocket-protocol)
13. [Error Codes](#13-error-codes)
14. [Rate Limiting](#14-rate-limiting)
15. [Pagination](#15-pagination)

---

## 1. Authentication

### JWT Bearer Tokens

All endpoints (except `/auth/*` and `/health`) require authentication via a JWT access token.

**Header format:**
```
Authorization: Bearer <access_token>
```

**Token flow:**
```
1. POST /auth/register  ──►  access_token + refresh_token
2. POST /auth/login     ──►  access_token + refresh_token
3. POST /auth/refresh   ──►  new access_token + refresh_token (rotation)
4. POST /auth/logout    ──►  revokes refresh token
```

| Token Type | Expiry | Audience | Usage |
|-----------|--------|----------|-------|
| Access token | 15 minutes | `forex-trading:access` | API authentication |
| Refresh token | 7 days | `forex-trading:refresh` | Obtain new access tokens |

### API Key Authentication

API keys are an alternative to JWT for programmatic access.

**Header format:**
```
X-API-Key: fx_key_<32-hex-chars>
```

**Key characteristics:**
- Prefixed with `fx_key_` for easy identification
- SHA-256 hashed before storage (never stored in plaintext)
- Shown exactly once at creation
- Support rotation with configurable grace period (5 min default)

### Error Responses

```json
{
  "detail": "Not authenticated",
  "code": "AUTH_REQUIRED"
}
```

```json
{
  "detail": "Token expired",
  "code": "TOKEN_EXPIRED"
}
```

---

## 2. Auth Endpoints

### `POST /auth/register`

Create a new user account.

**Request Body:**
```json
{
  "email": "trader@example.com",
  "username": "trader1",
  "password": "SecureP@ss123!"
}
```

**Response** `201 Created`:
```json
{
  "user_id": "uuid",
  "email": "trader@example.com",
  "username": "trader1",
  "role": "viewer",
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "expires_in": 900
}
```

**Errors:**
- `409 Conflict` — Email or username already registered
- `422 Unprocessable Entity` — Validation error

---

### `POST /auth/login`

Authenticate with email/username and password.

**Request Body:**
```json
{
  "username": "trader1",
  "password": "SecureP@ss123!"
}
```

**Response** `200 OK`:
```json
{
  "user_id": "uuid",
  "email": "trader@example.com",
  "username": "trader1",
  "role": "trader",
  "mfa_required": false,
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "expires_in": 900
}
```

**Errors:**
- `401 Unauthorized` — Invalid credentials
- `429 Too Many Requests` — Rate limit exceeded (10 req/min)

---

### `POST /auth/refresh`

Obtain a new token pair using a refresh token. Implements **single-use rotation** — the previous refresh token is revoked.

**Request Body:**
```json
{
  "refresh_token": "eyJhbG..."
}
```

**Response** `200 OK`:
```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Errors:**
- `401 Unauthorized` — Invalid or revoked refresh token

---

### `POST /auth/logout`

Revoke the current refresh token. Requires authentication.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "refresh_token": "eyJhbG..."
}
```

**Response** `200 OK`:
```json
{
  "message": "Successfully logged out"
}
```

---

### `POST /auth/mfa/setup`

Set up TOTP multi-factor authentication. Requires authentication (password re-entry).

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "password": "SecureP@ss123!"
}
```

**Response** `200 OK`:
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "qr_code_url": "otpauth://totp/ForexAI:trader@example.com?secret=...",
  "backup_codes": [
    "abc123def456",
    "789ghi012jkl",
    "..."
  ]
}
```

---

### `POST /auth/mfa/verify`

Verify a TOTP code (used during login if MFA is enabled).

**Request Body:**
```json
{
  "user_id": "uuid",
  "totp_code": "123456"
}
```

**Response** `200 OK`:
```json
{
  "verified": true,
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG..."
}
```

---

### `POST /auth/password/change`

Change the current user's password.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "current_password": "OldP@ss123!",
  "new_password": "NewP@ss456!"
}
```

**Response** `200 OK`:
```json
{
  "message": "Password changed successfully"
}
```

---

### `POST /auth/password/reset`

Request a password reset email.

**Request Body:**
```json
{
  "email": "trader@example.com"
}
```

**Response** `200 OK`:
```json
{
  "message": "Password reset email sent"
}
```

---

### `POST /auth/password/reset/confirm`

Complete password reset with token.

**Request Body:**
```json
{
  "token": "reset-token-from-email",
  "new_password": "NewP@ss456!"
}
```

**Response** `200 OK`:
```json
{
  "message": "Password reset successful"
}
```

---

## 3. Trading Endpoints

### `GET /trading/orders`

List orders with optional filtering.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |
| `status` | string | No | Filter by status (pending, new, filled, cancelled, rejected) |
| `symbol` | string | No | Filter by symbol (e.g., EURUSD) |
| `side` | string | No | Filter by side (buy, sell) |
| `limit` | int | No | Page size (default: 20, max: 100) |
| `offset` | int | No | Pagination offset (default: 0) |
| `from_date` | ISO datetime | No | Start date filter |
| `to_date` | ISO datetime | No | End date filter |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "order_id": "uuid",
      "symbol": "EURUSD",
      "side": "buy",
      "type": "market",
      "quantity": 0.1,
      "filled_quantity": 0.1,
      "price": null,
      "filled_price": 1.1045,
      "status": "filled",
      "stop_loss": 1.0990,
      "take_profit": 1.1150,
      "created_at": "2026-07-14T10:30:00Z",
      "filled_at": "2026-07-14T10:30:01Z",
      "broker_order_id": "oanda-12345"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### `POST /trading/orders`

Place a new order. The order passes through the Risk Engine before execution.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "broker_account_id": "uuid",
  "symbol": "EURUSD",
  "side": "buy",
  "type": "market",
  "quantity": 0.1,
  "stop_loss": 1.0990,
  "take_profit": 1.1150
}
```

**Response** `201 Created`:
```json
{
  "order_id": "uuid",
  "symbol": "EURUSD",
  "side": "buy",
  "quantity": 0.1,
  "status": "pending",
  "risk_assessment": {
    "is_approved": true,
    "risk_score": 0.15,
    "warnings": ["Spread is 2.5 pips — acceptable"]
  },
  "created_at": "2026-07-14T10:30:00Z"
}
```

**Errors:**
- `400 Bad Request` — Risk engine rejected the trade (includes violations list)
- `422 Unprocessable Entity` — Validation error
- `429 Too Many Requests` — Rate limit

---

### `GET /trading/orders/{order_id}`

Get detailed order information.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "order_id": "uuid",
  "symbol": "EURUSD",
  "side": "buy",
  "quantity": 0.1,
  "status": "filled",
  "price": 1.1045,
  "filled_price": 1.1045,
  "filled_quantity": 0.1,
  "commission": -0.50,
  "swap": 0.00,
  "stop_loss": 1.0990,
  "take_profit": 1.1150,
  "created_at": "2026-07-14T10:30:00Z",
  "filled_at": "2026-07-14T10:30:01Z",
  "closed_at": null,
  "broker_order_id": "oanda-12345",
  "strategy": "TrendFollowing",
  "ai_decision_id": "uuid"
}
```

---

### `DELETE /trading/orders/{order_id}`

Cancel a pending/new order.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "message": "Order cancelled",
  "order_id": "uuid"
}
```

---

### `PUT /trading/orders/{order_id}`

Modify a pending order (stop loss, take profit).

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "stop_loss": 1.0980,
  "take_profit": 1.1160
}
```

**Response** `200 OK`:
```json
{
  "order_id": "uuid",
  "status": "modified",
  "stop_loss": 1.0980,
  "take_profit": 1.1160
}
```

---

### `GET /trading/positions`

List open positions.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |
| `symbol` | string | No | Filter by symbol |
| `side` | string | No | Filter by side |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "position_id": "uuid",
      "symbol": "EURUSD",
      "side": "buy",
      "size": 0.1,
      "entry_price": 1.1045,
      "current_price": 1.1060,
      "unrealized_pnl": 15.00,
      "realized_pnl": 0.00,
      "stop_loss": 1.0990,
      "take_profit": 1.1150,
      "open_time": "2026-07-14T10:30:00Z",
      "duration_minutes": 45,
      "strategy": "TrendFollowing"
    }
  ],
  "total": 3
}
```

---

### `POST /trading/positions/{position_id}/close`

Close an open position.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "size": 0.1
}
```

**Response** `200 OK`:
```json
{
  "position_id": "uuid",
  "status": "closing",
  "realized_pnl": 15.00,
  "close_price": 1.1060
}
```

---

### `PUT /trading/positions/{position_id}/stop-loss`

Update stop loss on an open position.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "stop_loss": 1.1000
}
```

**Response** `200 OK`:
```json
{
  "position_id": "uuid",
  "stop_loss": 1.1000,
  "message": "Stop loss updated"
}
```

---

### `PUT /trading/positions/{position_id}/take-profit`

Update take profit on an open position.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "take_profit": 1.1200
}

```

**Response** `200 OK`:
```json
{
  "position_id": "uuid",
  "take_profit": 1.1200,
  "message": "Take profit updated"
}
```

---

### `GET /trading/deals`

List closed deals (completed trades).

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |
| `limit` | int | No | Page size (default: 20) |
| `offset` | int | No | Pagination offset |
| `from_date` | ISO datetime | No | Start date |
| `to_date` | ISO datetime | No | End date |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "deal_id": "uuid",
      "position_id": "uuid",
      "symbol": "EURUSD",
      "side": "buy",
      "size": 0.1,
      "entry_price": 1.1045,
      "exit_price": 1.1150,
      "pnl": 105.00,
      "pnl_pips": 105,
      "commission": -0.50,
      "swap": -0.10,
      "net_pnl": 104.40,
      "roi_pct": 0.95,
      "entry_time": "2026-07-14T10:30:00Z",
      "exit_time": "2026-07-14T14:30:00Z",
      "duration_minutes": 240,
      "strategy": "TrendFollowing",
      "exit_reason": "take_profit"
    }
  ],
  "total": 150
}
```

---

## 4. Risk Management Endpoints

### `GET /risk/state`

Get current risk state for an account.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |

**Response** `200 OK`:
```json
{
  "account_id": "uuid",
  "circuit_breaker": "closed",
  "daily_pnl": 150.00,
  "daily_drawdown_pct": 0.5,
  "total_drawdown_pct": 1.2,
  "total_exposure_pct": 5.0,
  "open_positions_count": 3,
  "consecutive_losses": 0,
  "daily_trades_count": 8,
  "last_risk_assessment": "2026-07-14T14:30:00Z",
  "updated_at": "2026-07-14T14:30:00Z"
}
```

---

### `GET /risk/config`

Get risk configuration for an account.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |

**Response** `200 OK`:
```json
{
  "account_id": "uuid",
  "max_position_size_pct": 2.0,
  "max_total_exposure_pct": 20.0,
  "max_positions": 10,
  "daily_drawdown_limit_pct": 3.0,
  "max_drawdown_limit_pct": 15.0,
  "max_exposure_per_pair_pct": 5.0,
  "max_consecutive_losses": 5,
  "max_spread_pips": 5.0,
  "cooldown_minutes": 60,
  "max_daily_trades": 50,
  "updated_at": "2026-07-14T10:00:00Z"
}
```

---

### `PUT /risk/config` (Admin, Trader)

Update risk configuration. Requires `admin` or `trader` role.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "broker_account_id": "uuid",
  "max_position_size_pct": 3.0,
  "max_total_exposure_pct": 25.0,
  "max_consecutive_losses": 3
}
```

**Response** `200 OK`:
```json
{
  "message": "Risk config updated",
  "changes": {
    "max_position_size_pct": "2.0 → 3.0",
    "max_total_exposure_pct": "20.0 → 25.0",
    "max_consecutive_losses": "5 → 3"
  }
}
```

**Errors:**
- `403 Forbidden` — Insufficient permissions
- `422 Unprocessable Entity` — Validation error

---

### `GET /risk/alerts`

List risk alerts for an account.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |
| `level` | string | No | Filter by level: `info`, `warning`, `critical` |
| `limit` | int | No | Page size (default: 20) |
| `offset` | int | No | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "alert_id": "uuid",
      "level": "warning",
      "category": "drawdown",
      "message": "Daily drawdown at 2.5% (limit: 3.0%)",
      "details": {
        "current_drawdown": 2.5,
        "limit": 3.0,
        "account_balance": 10000.00
      },
      "created_at": "2026-07-14T11:00:00Z",
      "acknowledged": false
    }
  ],
  "total": 5
}
```

---

### `POST /risk/circuit-breaker/reset` (Admin)

Reset the circuit breaker, transitioning from OPEN → CLOSED (or HALF_OPEN → CLOSED).

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "broker_account_id": "uuid",
  "reason": "Manual override by admin after reviewing conditions"
}
```

**Response** `200 OK`:
```json
{
  "previous_state": "open",
  "current_state": "closed",
  "reset_at": "2026-07-14T14:00:00Z",
  "message": "Circuit breaker reset"
}
```

---

### `POST /risk/emergency-liquidate` (SuperAdmin)

Emergency liquidation of all open positions for an account.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "broker_account_id": "uuid",
  "reason": "Critical system anomaly — emergency shutdown",
  "confirm": true
}
```

**Response** `200 OK`:
```json
{
  "total_positions_closed": 3,
  "total_pnl": -150.00,
  "message": "Emergency liquidation completed"
}
```

---

### `GET /risk/exposure`

Get current exposure breakdown.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `broker_account_id` | UUID | Yes | Broker account identifier |

**Response** `200 OK`:
```json
{
  "total_exposure_pct": 5.0,
  "total_exposure_usd": 500.00,
  "per_symbol": [
    {
      "symbol": "EURUSD",
      "exposure_pct": 2.0,
      "exposure_usd": 200.00,
      "positions_count": 1
    },
    {
      "symbol": "GBPUSD",
      "exposure_pct": 3.0,
      "exposure_usd": 300.00,
      "positions_count": 2
    }
  ],
  "correlated_exposure_pct": 4.0,
  "correlated_exposure_usd": 400.00
}
```

---

## 5. Broker Endpoints

### `GET /broker/accounts`

List connected broker accounts.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "items": [
    {
      "account_id": "uuid",
      "broker_name": "OANDA",
      "account_type": "practice",
      "account_number": "001-001-12345678-001",
      "balance": 100000.00,
      "equity": 100500.00,
      "margin_used": 500.00,
      "margin_free": 100000.00,
      "leverage": 50,
      "currency": "USD",
      "is_connected": true,
      "status": "active",
      "last_sync_at": "2026-07-14T14:30:00Z",
      "created_at": "2026-07-01T00:00:00Z"
    }
  ]
}
```

---

### `POST /broker/accounts`

Connect a new broker account.

**Headers:** `Authorization: Bearer <access_token>`

**Request Body:**
```json
{
  "broker_name": "OANDA",
  "account_type": "practice",
  "api_key": "your-oanda-api-key",
  "account_id": "001-001-12345678-001",
  "environment": "practice"
}
```

**Response** `201 Created`:
```json
{
  "account_id": "uuid",
  "broker_name": "OANDA",
  "status": "connected",
  "message": "Broker account connected successfully"
}
```

---

### `GET /broker/accounts/{account_id}`

Get broker account details.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "account_id": "uuid",
  "broker_name": "OANDA",
  "status": "active",
  "balance": 100000.00,
  "equity": 100500.00,
  "unrealized_pnl": 500.00,
  "margin_level_pct": 20100.0,
  "open_positions": 3,
  "pending_orders": 1,
  "last_sync_at": "2026-07-14T14:30:00Z"
}
```

---

### `DELETE /broker/accounts/{account_id}`

Disconnect and remove a broker account.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "message": "Broker account disconnected",
  "account_id": "uuid"
}
```

---

### `POST /broker/accounts/{account_id}/sync`

Force re-sync of broker account data.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "message": "Sync initiated",
  "account_id": "uuid",
  "last_sync_at": "2026-07-14T14:35:00Z"
}
```

---

## 6. Market Data Endpoints

### `GET /market/symbols`

List available trading symbols.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "items": [
    {"symbol": "EURUSD", "description": "Euro vs US Dollar", "digits": 5, "pip_value": 0.0001},
    {"symbol": "GBPUSD", "description": "British Pound vs US Dollar", "digits": 5, "pip_value": 0.0001},
    {"symbol": "USDJPY", "description": "US Dollar vs Japanese Yen", "digits": 3, "pip_value": 0.01},
    {"symbol": "AUDUSD", "description": "Australian Dollar vs US Dollar", "digits": 5, "pip_value": 0.0001},
    {"symbol": "USDCAD", "description": "US Dollar vs Canadian Dollar", "digits": 5, "pip_value": 0.0001},
    {"symbol": "GBPJPY", "description": "British Pound vs Japanese Yen", "digits": 3, "pip_value": 0.01},
    {"symbol": "XAUUSD", "description": "Gold vs US Dollar", "digits": 2, "pip_value": 0.01}
  ]
}
```

---

### `GET /market/quotes/{symbol}`

Get current quote for a symbol.

**Headers:** `Authorization: Bearer <access_token>`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Forex pair (e.g., EURUSD) |

**Response** `200 OK`:
```json
{
  "symbol": "EURUSD",
  "bid": 1.10450,
  "ask": 1.10455,
  "spread": 0.5,
  "high": 1.10600,
  "low": 1.10200,
  "volume": 15000,
  "timestamp": "2026-07-14T14:30:00.123Z"
}
```

---

### `GET /market/candles/{symbol}`

Get historical OHLCV candles.

**Headers:** `Authorization: Bearer <access_token>`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Forex pair (e.g., EURUSD) |

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timeframe` | string | No | `H1` | M1, M5, M15, M30, H1, H4, D1, W1 |
| `limit` | int | No | `100` | Number of candles (max: 500) |
| `from_date` | ISO datetime | No | — | Start date |
| `to_date` | ISO datetime | No | — | End date |

**Response** `200 OK`:
```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles": [
    {
      "timestamp": "2026-07-14T13:00:00Z",
      "open": 1.10400,
      "high": 1.10480,
      "low": 1.10350,
      "close": 1.10450,
      "volume": 12500
    }
  ]
}
```

---

### `GET /market/structure/{symbol}`

Get market structure analysis (SMC).

**Headers:** `Authorization: Bearer <access_token>`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Forex pair (e.g., EURUSD) |

**Response** `200 OK`:
```json
{
  "symbol": "EURUSD",
  "regime": "TRENDING_UP",
  "session": "london",
  "swing_highs": [
    {"price": 1.10600, "timestamp": "2026-07-14T12:00:00Z"}
  ],
  "swing_lows": [
    {"price": 1.10200, "timestamp": "2026-07-14T10:00:00Z"}
  ],
  "order_blocks": [
    {"price": 1.10350, "type": "bullish", "strength": 0.8}
  ],
  "fair_value_gaps": [
    {"price_range": {"from": 1.10400, "to": 1.10420}, "filled": false}
  ],
  "liquidity_zones": [
    {"price": 1.10650, "type": "buy-side", "strength": 0.7}
  ],
  "market_regime": {
    "trend": "bullish",
    "strength": 0.75,
    "volatility": "normal"
  }
}
```

---

## 7. Strategy Endpoints

### `GET /strategy/list`

List all available strategies.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "strategies": [
    {
      "name": "TrendFollowing",
      "display_name": "Trend Following",
      "description": "Follows established trends using EMA alignment and ADX filter",
      "optimal_regimes": ["TRENDING_UP", "TRENDING_DOWN"],
      "min_confidence": 0.6,
      "parameters": {
        "fast_ema_period": 20,
        "slow_ema_period": 50,
        "adx_threshold": 25,
        "min_rr_ratio": 2.0
      },
      "is_active": true
    }
  ]
}
```

---

### `GET /strategy/active`

Get the currently active strategy.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No | Filter by symbol |

**Response** `200 OK`:
```json
{
  "symbol": "EURUSD",
  "current_strategy": "TrendFollowing",
  "reason": "Market in TRENDING_UP regime with ADX 32",
  "regime": "TRENDING_UP",
  "performance": {
    "win_rate": 0.65,
    "profit_factor": 1.8,
    "total_trades": 42,
    "avg_duration_minutes": 180,
    "sharpe_ratio": 1.2
  }
}
```

---

## 8. AI Endpoints

### `GET /ai/decisions`

List recent AI trading decisions.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No | Filter by symbol |
| `limit` | int | No | Page size (default: 20) |
| `offset` | int | No | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "decision_id": "uuid",
      "symbol": "EURUSD",
      "direction": "long",
      "confidence": 0.78,
      "agreement_ratio": 0.72,
      "consensus": "LONG",
      "market_regime": "TRENDING_UP",
      "agent_count": 9,
      "agents_agreeing": 6,
      "agents_disagreeing": 2,
      "agents_neutral": 1,
      "explanation": {
        "summary": "Bullish consensus driven by strong trend and market structure alignment.",
        "key_factors": [
          "Trend agent detected EMA20/50 bullish crossover with ADX 32",
          "Market structure shows BOS above previous swing high",
          "Liquidity agent identified buy-side liquidity above 1.1060"
        ],
        "agent_contributions": {
          "market_structure": {"weight": 0.90, "vote": "LONG", "confidence": 0.85},
          "trend_ai": {"weight": 0.90, "vote": "LONG", "confidence": 0.88},
          "liquidity_ai": {"weight": 0.80, "vote": "LONG", "confidence": 0.75},
          "sentiment_ai": {"weight": 0.75, "vote": "NEUTRAL", "confidence": 0.50},
          "risk_ai": {"weight": 0.95, "vote": "LONG", "confidence": 0.90}
        }
      },
      "was_executed": true,
      "executed_order_id": "uuid",
      "created_at": "2026-07-14T14:00:00Z"
    }
  ],
  "total": 85
}
```

---

### `GET /ai/agents`

List available AI agents with their status.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "agents": [
    {
      "agent_id": "market_structure",
      "name": "Market Structure Agent",
      "focus": "ICT/SMC swing analysis, BOS, CHoCH",
      "status": "active",
      "current_weight": 0.90,
      "performance": {
        "win_rate": 0.62,
        "avg_confidence": 0.78,
        "total_decisions": 150
      }
    }
  ]
}
```

---

### `GET /ai/performance`

Get AI agent performance statistics.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | No | Filter by agent |
| `days` | int | No | Lookback period (default: 30) |

**Response** `200 OK`:
```json
{
  "period_days": 30,
  "agents": [
    {
      "agent_id": "market_structure",
      "total_signals": 150,
      "correct_predictions": 93,
      "win_rate": 0.62,
      "avg_confidence": 0.78,
      "current_weight": 0.90,
      "weight_trend": "stable"
    }
  ]
}
```

---

## 9. Account Endpoints

### `GET /accounts/profile`

Get the current user's profile.

**Headers:** `Authorization: Bearer <access_token>`

**Response** `200 OK`:
```json
{
  "user_id": "uuid",
  "username": "trader1",
  "email": "trader@example.com",
  "role": "trader",
  "mfa_enabled": true,
  "created_at": "2026-07-01T00:00:00Z",
  "last_login": "2026-07-14T10:00:00Z"
}
```

---

## 10. Analytics Endpoints

### `GET /analytics/summary`

Get trading performance summary.

**Headers:** `Authorization: Bearer <access_token>`

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `broker_account_id` | UUID | Yes | — | Account identifier |
| `period` | string | No | `30d` | `7d`, `30d`, `90d`, `all` |

**Response** `200 OK`:
```json
{
  "account_id": "uuid",
  "period": "30d",
  "total_trades": 42,
  "winning_trades": 27,
  "losing_trades": 15,
  "win_rate": 0.64,
  "total_pnl": 1250.00,
  "total_pnl_pips": 520,
  "profit_factor": 1.85,
  "avg_win": 85.00,
  "avg_loss": -35.00,
  "largest_win": 250.00,
  "largest_loss": -80.00,
  "avg_duration_minutes": 180,
  "sharpe_ratio": 1.2,
  "max_drawdown_pct": 2.1,
  "roi_pct": 1.25,
  "strategy_breakdown": [
    {"strategy": "TrendFollowing", "trades": 20, "win_rate": 0.70, "pnl": 900.00},
    {"strategy": "Pullback", "trades": 15, "win_rate": 0.60, "pnl": 350.00}
  ],
  "symbol_breakdown": [
    {"symbol": "EURUSD", "trades": 25, "win_rate": 0.68, "pnl": 800.00},
    {"symbol": "GBPUSD", "trades": 17, "win_rate": 0.59, "pnl": 450.00}
  ]
}
```

---

## 11. Monitoring Endpoints

### `GET /health`

Basic health check — no authentication required.

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

### `GET /health/live`

Kubernetes liveness probe.

**Response** `200 OK`:
```json
{
  "status": "alive"
}
```

---

### `GET /health/ready`

Kubernetes readiness probe with dependency checks.

**Response** `200 OK`:
```json
{
  "status": "ok",
  "checks": {
    "app": "ok",
    "database": "ok",
    "cache": "ok",
    "event_bus": "ok",
    "rate_limiter": "ok"
  }
}
```

**Response** `503 Service Unavailable` (when degraded):
```json
{
  "status": "degraded",
  "checks": {
    "app": "ok",
    "database": "ok",
    "cache": "error",
    "event_bus": "ok",
    "rate_limiter": "ok"
  }
}
```

---

### `GET /health/detailed`

Detailed health information.

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

---

### `GET /metrics`

Prometheus metrics endpoint.

**Response** `200 OK` (Content-Type: `text/plain; version=0.0.4`):
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health",status="200"} 42.0
http_requests_total{method="POST",endpoint="/auth/login",status="200"} 15.0
...
```

---

### `GET /system/info`

Get system information.

**Response** `200 OK`:
```json
{
  "api_version": "v1",
  "environment": "development",
  "services": {
    "market_data": "operational",
    "ai_orchestrator": "operational",
    "strategy_engine": "operational",
    "risk_engine": "operational",
    "execution_engine": "operational"
  }
}
```

---

## 12. WebSocket Protocol

### Connection

Connect to the WebSocket endpoint with a JWT access token:

```
ws://localhost:8000/ws?token=<access_token>
```

Per-channel endpoints (legacy):
```
ws://localhost:8000/ws/market/{symbol}?token=<token>
ws://localhost:8000/ws/orders/{account_id}?token=<token>
ws://localhost:8000/ws/positions/{account_id}?token=<token>
ws://localhost:8000/ws/signals?token=<token>
ws://localhost:8000/ws/alerts?token=<token>
ws://localhost:8000/ws/dashboard?token=<token>
```

### Channels

| Channel | Description | Message Types |
|---------|-------------|---------------|
| `ticks` | Real-time bid/ask prices | `tick` |
| `positions` | Position updates | `position_opened`, `position_updated`, `position_closed` |
| `orders` | Order status changes | `order_new`, `order_filled`, `order_cancelled`, `order_rejected` |
| `risk` | Risk alerts and warnings | `alert`, `circuit_breaker` |
| `signals` | AI trading signals | `signal` |
| `session` | Trading session changes | `session_start`, `session_end`, `regime_change` |
| `dashboard` | All channels combined | All of the above |

### Client Messages

#### Subscribe
```json
{
  "action": "subscribe",
  "channel": "ticks",
  "symbols": ["EURUSD", "GBPUSD"]
}
```

#### Unsubscribe
```json
{
  "action": "unsubscribe",
  "channel": "ticks",
  "symbols": ["GBPUSD"]
}
```

#### Ping
```json
{
  "action": "ping"
}
```

### Server Messages

#### Connection Established
```json
{
  "type": "connected",
  "connection_id": "uuid",
  "message": "Connected to Forex Trading Bot real-time feed"
}
```

#### Tick Update
```json
{
  "type": "tick",
  "channel": "ticks",
  "data": {
    "symbol": "EURUSD",
    "bid": 1.10450,
    "ask": 1.10455,
    "spread": 0.5,
    "timestamp": "2026-07-14T14:30:00.123Z"
  }
}
```

#### Position Update
```json
{
  "type": "position_opened",
  "channel": "positions",
  "data": {
    "position_id": "uuid",
    "symbol": "EURUSD",
    "side": "buy",
    "size": 0.1,
    "entry_price": 1.1045,
    "stop_loss": 1.0990,
    "take_profit": 1.1150,
    "open_time": "2026-07-14T14:30:00Z"
  }
}
```

#### AI Signal
```json
{
  "type": "signal",
  "channel": "signals",
  "data": {
    "symbol": "EURUSD",
    "direction": "long",
    "confidence": 0.78,
    "agreement_ratio": 0.72,
    "entry_price": 1.1045,
    "stop_loss": 1.0990,
    "take_profit": 1.1150,
    "rationale": "Bullish consensus driven by strong trend alignment...",
    "agent_count": 9,
    "timestamp": "2026-07-14T14:30:00Z"
  }
}
```

#### Risk Alert
```json
{
  "type": "alert",
  "channel": "risk",
  "data": {
    "level": "warning",
    "category": "drawdown",
    "message": "Daily drawdown approaching limit (2.5% / 3.0%)",
    "timestamp": "2026-07-14T14:30:00Z"
  }
}
```

#### Error
```json
{
  "type": "error",
  "detail": "Message exceeds maximum size of 65536 bytes"
}
```

### Rate Limits

- Maximum message size: 65,536 bytes (64 KB)
- Maximum symbols per tick subscription: 50
- Connection timeout: N/A (keep-alive via ping)

---

## 13. Error Codes

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `201` | Created |
| `204` | No Content |
| `400` | Bad Request — Invalid input or risk rejection |
| `401` | Unauthorized — Missing or invalid authentication |
| `403` | Forbidden — Insufficient permissions |
| `404` | Not Found |
| `409` | Conflict — Duplicate resource |
| `422` | Unprocessable Entity — Validation error |
| `429` | Too Many Requests — Rate limit exceeded |
| `500` | Internal Server Error |
| `503` | Service Unavailable — Dependency unhealthy |

### Error Response Format

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "errors": [
    {
      "field": "symbol",
      "message": "Invalid forex pair format"
    }
  ]
}
```

### Application Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_REQUIRED` | 401 | No authentication provided |
| `TOKEN_EXPIRED` | 401 | JWT token has expired |
| `TOKEN_REVOKED` | 401 | Token has been revoked |
| `INVALID_CREDENTIALS` | 401 | Wrong email/password |
| `MFA_REQUIRED` | 401 | MFA verification needed |
| `INSUFFICIENT_PERMISSIONS` | 403 | Role lacks required permissions |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource does not exist |
| `EMAIL_EXISTS` | 409 | Email already registered |
| `USERNAME_EXISTS` | 409 | Username already taken |
| `VALIDATION_ERROR` | 422 | Input validation failed |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `RISK_REJECTED` | 400 | Trade rejected by risk engine |
| `CIRCUIT_BREAKER_OPEN` | 400 | Circuit breaker is active |
| `BROKER_DISCONNECTED` | 400 | Broker account not connected |
| `INSUFFICIENT_MARGIN` | 400 | Not enough margin for trade |
| `ORDER_NOT_MODIFIABLE` | 400 | Order cannot be modified in current state |
| `POSITION_NOT_CLOSEABLE` | 400 | Position cannot be closed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `SERVICE_UNAVAILABLE` | 503 | Downstream dependency unavailable |

---

## 14. Rate Limiting

### Default Limits

| Scope | Limit | Window |
|-------|-------|--------|
| General API (per IP) | 100 requests | 60 seconds |
| Login (per IP) | 10 requests | 60 seconds |
| Trading (per user) | 60 requests | 60 seconds |
| WebSocket messages | 60 messages | 60 seconds |

### Response

When rate limited, the API returns `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded. Try again in 45 seconds.",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after_seconds": 45
}
```

**Headers:**
```
Retry-After: 45
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1626270000
```

### Configuration

Rate limits are configured per-route in `DEFAULT_RULES`:

| Route Pattern | Max Requests | Window | Per User | Per IP | Per API Key |
|--------------|-------------|--------|----------|--------|-------------|
| `/api/v1/auth/login` | 10 | 60s | No | Yes | No |
| `/api/v1/auth/register` | 5 | 60s | No | Yes | No |
| `/api/v1/auth/*` | 20 | 60s | Yes | Yes | No |
| `/api/v1/trading/*` | 60 | 60s | Yes | Yes | Yes |
| `/api/v1/risk/*` | 30 | 60s | Yes | Yes | Yes |
| `/api/v1/market/*` | 120 | 60s | Yes | Yes | Yes |
| `/api/v1/*` (default) | 100 | 60s | Yes | Yes | Yes |

---

## 15. Pagination

All list endpoints use cursor-less pagination with `limit` and `offset` parameters.

### Request

```
GET /api/v1/trading/orders?limit=20&offset=40
```

### Response

```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "offset": 40
}
```

### Parameters

| Parameter | Type | Default | Maximum | Description |
|-----------|------|---------|---------|-------------|
| `limit` | int | 20 | 100 | Number of items per page |
| `offset` | int | 0 | — | Number of items to skip |

### Calculating Pages

```python
page = (offset / limit) + 1
total_pages = ceil(total / limit)
has_next = offset + limit < total
has_prev = offset > 0
```
