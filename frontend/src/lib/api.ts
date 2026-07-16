// Type-safe API client for the Forex Trading backend
import axios, { AxiosError, type AxiosInstance } from 'axios';
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
  UserListResponse,
  AdminResetPasswordRequest,
  PaginatedResponse,
  OrdersParams,
  PlaceOrderRequest,
  ClosePositionRequest,
  OrderResponse,
  BacktestConfig,
  BacktestResult,
  EquityPoint,
  PortfolioMetrics,
  AISignal,
} from '@/types/api';
import type { Position, Order } from '@/types/trading';
import type {
  Candle,
  Tick,
  SessionInfo,
  MarketStructure,
  CurrencyStrength,
  RiskState,
  RiskAlert,
  RiskConfig,
} from '@/types/market';

// Demo mode mock data fallback
import {
  MOCK_ACCOUNT,
  MOCK_POSITIONS,
  MOCK_ORDERS,
  MOCK_AI_SIGNAL,
  MOCK_SESSION_INFO,
  MOCK_RISK_STATE,
  MOCK_RISK_ALERTS,
  MOCK_RISK_CONFIG,
  MOCK_PORTFOLIO_METRICS,
  generateMockEquityCurve,
  generateMockCandles,
  generateMockMonthlyReturns,
} from '@/lib/mockData';

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const axiosInstance: AxiosInstance = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach auth token from local storage on every request
axiosInstance.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401 → clear tokens and fall back gracefully
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
    return Promise.reject(error);
  }
);

// ---------------------------------------------------------------------------
// Helper: demo fallback wrapper
// ---------------------------------------------------------------------------

async function withDemoFallback<T>(
  apiFn: () => Promise<T>,
  mockData: T | (() => T)
): Promise<T> {
  if (DEMO_MODE) {
    await new Promise((r) => setTimeout(r, 200 + Math.random() * 300));
    return typeof mockData === 'function' ? (mockData as () => T)() : mockData;
  }
  try {
    return await apiFn();
  } catch (err) {
    const axErr = err as AxiosError;
    if (!axErr.response || axErr.code === 'ECONNABORTED' || axErr.code === 'ERR_NETWORK' || axErr.response?.status === 401) {
      console.warn('[API] Backend unavailable or unauthorized, using demo data');
      return typeof mockData === 'function' ? (mockData as () => T)() : mockData;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

async function login(credentials: LoginRequest): Promise<LoginResponse> {
  if (DEMO_MODE) {
    // Demo login always succeeds
    const mockResp: LoginResponse = {
      access_token: 'demo_token',
      refresh_token: 'demo_refresh',
      token_type: 'bearer',
      expires_in: 900,
      user: {
        id: 'demo_user',
        email: 'demo@forexbot.ai',
        username: 'demo',
        full_name: 'Demo Trader',
        role: 'trader',
        is_active: true,
        mfa_enabled: false,
        created_at: new Date().toISOString(),
      },
    };
    localStorage.setItem('access_token', mockResp.access_token);
    localStorage.setItem('refresh_token', mockResp.refresh_token);
    return mockResp;
  }
  const res = await axiosInstance.post<LoginResponse>('/auth/login', credentials);
  localStorage.setItem('access_token', res.data.access_token);
  localStorage.setItem('refresh_token', res.data.refresh_token);
  return res.data;
}

async function register(data: RegisterRequest): Promise<LoginResponse> {
  if (DEMO_MODE) {
    const mockResp: LoginResponse = {
      access_token: 'demo_token',
      refresh_token: 'demo_refresh',
      token_type: 'bearer',
      expires_in: 900,
      user: {
        id: 'demo_user_' + Date.now(),
        email: data.email,
        username: data.username,
        full_name: data.full_name || undefined,
        role: 'trader',
        is_active: true,
        mfa_enabled: false,
        created_at: new Date().toISOString(),
      },
    };
    localStorage.setItem('access_token', mockResp.access_token);
    localStorage.setItem('refresh_token', mockResp.refresh_token);
    return mockResp;
  }
  const res = await axiosInstance.post<LoginResponse>('/auth/register', data);
  localStorage.setItem('access_token', res.data.access_token);
  localStorage.setItem('refresh_token', res.data.refresh_token);
  return res.data;
}

async function requestPasswordReset(email: string): Promise<void> {
  if (DEMO_MODE) {
    return;
  }
  await axiosInstance.post('/auth/password-reset/request', { email });
}

async function confirmPasswordReset(token: string, new_password: string): Promise<void> {
  if (DEMO_MODE) {
    return;
  }
  await axiosInstance.post('/auth/password-reset/reset', { token, new_password });
}

async function logout(): Promise<void> {
  if (!DEMO_MODE) {
    try {
      await axiosInstance.post('/auth/logout');
    } catch {
      // ignore errors
    }
  }
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

async function refresh(): Promise<LoginResponse> {
  const refreshToken = localStorage.getItem('refresh_token');
  const res = await axiosInstance.post<LoginResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });
  return res.data;
}

async function me(): Promise<User> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<User>('/auth/me');
      return res.data;
    },
    {
      id: 'demo_user',
      email: 'demo@forexbot.ai',
      username: 'demo',
      full_name: 'Demo Trader',
      role: 'trader',
      is_active: true,
      mfa_enabled: false,
      created_at: new Date().toISOString(),
    }
  );
}

// ---------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------

async function getAccountSummary() {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get('/accounts/summary');
      return res.data;
    },
    MOCK_ACCOUNT
  );
}

// ---------------------------------------------------------------------------
// Trading
// ---------------------------------------------------------------------------

async function getPositions(): Promise<Position[]> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<Position[]>('/trading/positions');
      return res.data;
    },
    MOCK_POSITIONS
  );
}

async function getOrders(params?: OrdersParams): Promise<PaginatedResponse<Order>> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<PaginatedResponse<Order>>('/trading/orders', { params });
      return res.data;
    },
    {
      items: MOCK_ORDERS,
      total: MOCK_ORDERS.length,
      page: 1,
      page_size: 50,
      pages: 1,
    }
  );
}

async function placeOrder(order: PlaceOrderRequest): Promise<OrderResponse> {
  if (DEMO_MODE) {
    return {
      order_id: `ORD${Date.now()}`,
      symbol: order.symbol,
      side: order.side,
      quantity: order.quantity,
      status: 'filled',
      filled_price: undefined,
      created_at: new Date().toISOString(),
    };
  }
  const res = await axiosInstance.post<OrderResponse>('/trading/orders', order);
  return res.data;
}

async function closePosition(id: string, req: ClosePositionRequest): Promise<boolean> {
  if (DEMO_MODE) return true;
  const res = await axiosInstance.post(`/trading/positions/${id}/close`, req);
  return res.status === 200;
}

async function updateStopLoss(id: string, price: number): Promise<boolean> {
  if (DEMO_MODE) return true;
  const res = await axiosInstance.patch(`/trading/positions/${id}/stop-loss`, {
    stop_loss: price,
  });
  return res.status === 200;
}

async function updateTakeProfit(id: string, price: number): Promise<boolean> {
  if (DEMO_MODE) return true;
  const res = await axiosInstance.patch(`/trading/positions/${id}/take-profit`, {
    take_profit: price,
  });
  return res.status === 200;
}

// ---------------------------------------------------------------------------
// Market Data
// ---------------------------------------------------------------------------

async function getCandles(symbol: string, timeframe: string, count = 200): Promise<Candle[]> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<Candle[]>('/market/candles', {
        params: { symbol, timeframe, count },
      });
      return res.data;
    },
    () => generateMockCandles(count, symbol)
  );
}

async function getTick(symbol: string): Promise<Tick> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<Tick>(`/market/tick/${symbol}`);
      return res.data;
    },
    {
      symbol,
      bid: 1.08234,
      ask: 1.08236,
      spread: 0.00002,
      timestamp: new Date().toISOString(),
    }
  );
}

async function getSession(): Promise<SessionInfo> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<SessionInfo>('/market/session');
      return res.data;
    },
    MOCK_SESSION_INFO
  );
}

async function getStructure(symbol: string): Promise<MarketStructure> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<MarketStructure>(`/market/structure/${symbol}`);
      return res.data;
    },
    {
      symbol,
      timeframe: 'H4',
      trend_direction: 'bullish',
      support_levels: [1.078, 1.0750],
      resistance_levels: [1.092, 1.0955],
      order_blocks: [],
      fair_value_gaps: [],
    }
  );
}

async function getCurrencyStrength(): Promise<Record<string, number>> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<CurrencyStrength[]>('/market/currency-strength');
      return Object.fromEntries(res.data.map((c) => [c.currency, c.strength_score]));
    },
    { USD: 72, EUR: 65, GBP: 58, JPY: 45, AUD: 52, NZD: 48, CAD: 55, CHF: 61 }
  );
}

// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

async function getRiskState(): Promise<RiskState> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<RiskState>('/risk/state');
      return res.data;
    },
    MOCK_RISK_STATE
  );
}

async function getRiskAlerts(): Promise<RiskAlert[]> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<RiskAlert[]>('/risk/alerts');
      return res.data;
    },
    MOCK_RISK_ALERTS
  );
}

async function getRiskConfig(): Promise<RiskConfig> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<RiskConfig>('/risk/config');
      return res.data;
    },
    MOCK_RISK_CONFIG
  );
}

async function updateRiskConfig(config: Partial<RiskConfig>): Promise<RiskConfig> {
  if (DEMO_MODE) return { ...MOCK_RISK_CONFIG, ...config };
  const res = await axiosInstance.patch<RiskConfig>('/risk/config', config);
  return res.data;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

async function getPortfolioMetrics(): Promise<PortfolioMetrics> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<PortfolioMetrics>('/analytics/metrics');
      return res.data;
    },
    MOCK_PORTFOLIO_METRICS
  );
}

async function getEquityCurve(granularity = 'daily'): Promise<EquityPoint[]> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<EquityPoint[]>('/analytics/equity-curve', {
        params: { granularity },
      });
      return res.data;
    },
    () => generateMockEquityCurve(90)
  );
}

async function getMonthlyReturns(): Promise<Record<string, number>> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<Record<string, number>>('/analytics/monthly-returns');
      return res.data;
    },
    () => generateMockMonthlyReturns()
  );
}

async function runBacktest(config: BacktestConfig): Promise<string> {
  if (DEMO_MODE) return `DEMO_BACKTEST_${Date.now()}`;
  const res = await axiosInstance.post<{ run_id: string }>('/analytics/backtest', config);
  return res.data.run_id;
}

async function getBacktestResult(runId: string): Promise<BacktestResult> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<BacktestResult>(`/analytics/backtest/${runId}`);
      return res.data;
    },
    {
      run_id: runId,
      status: 'completed',
      strategy: 'ICT_Momentum',
      symbol: 'EURUSD',
      timeframe: 'H1',
      start_date: '2023-01-01',
      end_date: '2023-12-31',
      initial_balance: 10_000,
      final_balance: 14_872,
      total_return_pct: 48.72,
      sharpe_ratio: 2.14,
      sortino_ratio: 3.22,
      max_drawdown_pct: 8.43,
      profit_factor: 2.34,
      win_rate: 67.4,
      total_trades: 187,
      winning_trades: 126,
      losing_trades: 61,
      avg_win_pct: 1.42,
      avg_loss_pct: -0.61,
      equity_curve: generateMockEquityCurve(252),
      monthly_returns: generateMockMonthlyReturns(),
      trades: [],
    }
  );
}

// ---------------------------------------------------------------------------
// AI Signals
// ---------------------------------------------------------------------------

async function getLatestSignal(): Promise<AISignal | null> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<AISignal>('/strategy/signals/latest');
      return res.data;
    },
    MOCK_AI_SIGNAL
  );
}

async function getSignals(limit = 10): Promise<AISignal[]> {
  return withDemoFallback(
    async () => {
      const res = await axiosInstance.get<AISignal[]>('/strategy/signals', {
        params: { limit },
      });
      return res.data;
    },
    [MOCK_AI_SIGNAL]
  );
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

async function adminListUsers(skip = 0, limit = 100): Promise<UserListResponse> {
  if (DEMO_MODE) {
    return {
      users: [
        { id: '1', email: 'admin@forexbot.ai', username: 'admin', full_name: 'Admin User', role: 'admin', is_active: true, mfa_enabled: false, created_at: '2025-01-01T00:00:00Z' },
        { id: '2', email: 'demo@forexbot.ai', username: 'demo', full_name: 'Demo Trader', role: 'trader', is_active: true, mfa_enabled: false, created_at: '2025-01-15T00:00:00Z' },
        { id: '3', email: 'trader@forexbot.ai', username: 'trader1', full_name: 'Active Trader', role: 'trader', is_active: true, mfa_enabled: false, created_at: '2025-02-01T00:00:00Z' },
        { id: '4', email: 'viewer@forexbot.ai', username: 'viewer1', full_name: 'Report Viewer', role: 'viewer', is_active: false, mfa_enabled: false, created_at: '2025-03-01T00:00:00Z' },
      ],
      total: 4,
    };
  }
  const res = await axiosInstance.get<UserListResponse>('/users/', { params: { skip, limit } });
  return res.data;
}

async function adminSearchUsers(q: string): Promise<UserListResponse> {
  if (DEMO_MODE) return adminListUsers();
  const res = await axiosInstance.get<UserListResponse>('/users/admin/search', { params: { q } });
  return res.data;
}

async function adminGetUser(userId: string): Promise<User> {
  if (DEMO_MODE) {
    const { users } = await adminListUsers();
    return users.find((u) => u.id === userId) || users[0];
  }
  const res = await axiosInstance.get<User>(`/users/${userId}`);
  return res.data;
}

async function adminUpdateUser(userId: string, data: Partial<User>): Promise<User> {
  if (DEMO_MODE) return { ...(await adminGetUser(userId)), ...data };
  const res = await axiosInstance.put<User>(`/users/${userId}`, data);
  return res.data;
}

async function adminUpdateRole(userId: string, role: string): Promise<User> {
  if (DEMO_MODE) return adminGetUser(userId);
  const res = await axiosInstance.put<User>(`/users/${userId}/role`, null, { params: { role } });
  return res.data;
}

async function adminToggleActive(userId: string): Promise<User> {
  if (DEMO_MODE) return adminGetUser(userId);
  const res = await axiosInstance.post<User>(`/users/${userId}/toggle-active`);
  return res.data;
}

async function adminResetUserPassword(userId: string, newPassword: string): Promise<void> {
  if (DEMO_MODE) return;
  await axiosInstance.post(`/users/${userId}/reset-password`, { new_password: newPassword });
}

// ---------------------------------------------------------------------------
// Exported API object
// ---------------------------------------------------------------------------

export const api = {
  auth: { login, register, requestPasswordReset, confirmPasswordReset, logout, refresh, me },
  account: { getAccountSummary },
  trading: {
    getPositions,
    getOrders,
    placeOrder,
    closePosition,
    updateStopLoss,
    updateTakeProfit,
  },
  market: {
    getCandles,
    getTick,
    getSession,
    getStructure,
    getCurrencyStrength,
  },
  risk: {
    getState: getRiskState,
    getAlerts: getRiskAlerts,
    getConfig: getRiskConfig,
    updateConfig: updateRiskConfig,
  },
  analytics: {
    getPortfolioMetrics,
    getEquityCurve,
    getMonthlyReturns,
    runBacktest,
    getBacktestResult,
  },
  signals: {
    getLatest: getLatestSignal,
    getAll: getSignals,
  },
  admin: {
    listUsers: adminListUsers,
    searchUsers: adminSearchUsers,
    getUser: adminGetUser,
    updateUser: adminUpdateUser,
    updateRole: adminUpdateRole,
    toggleActive: adminToggleActive,
    resetPassword: adminResetUserPassword,
  },
} as const;

export default api;
