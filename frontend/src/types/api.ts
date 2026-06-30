// API-level TypeScript types matching the FastAPI backend schemas

export interface LoginRequest {
  username: string;
  password: string;
  mfa_token?: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface User {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  role: 'admin' | 'trader' | 'viewer' | 'superadmin';
  is_active: boolean;
  is_verified?: boolean;
  mfa_enabled: boolean;
  last_login?: string;
  failed_login_attempts?: number;
  created_at: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface UserListResponse {
  users: User[];
  total: number;
}

export interface AdminResetPasswordRequest {
  new_password: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface OrdersParams {
  page?: number;
  page_size?: number;
  symbol?: string;
  status?: string;
  from_date?: string;
  to_date?: string;
}

export interface PlaceOrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  order_type: 'market' | 'limit' | 'stop' | 'stop_limit';
  price?: number;
  stop_loss?: number;
  take_profit?: number;
  comment?: string;
}

export interface ClosePositionRequest {
  partial_pct?: number;
  reason?: string;
}

export interface OrderResponse {
  order_id: string;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
  filled_price?: number;
  created_at: string;
}

export interface BacktestConfig {
  strategy: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  risk_pct: number;
  params?: Record<string, unknown>;
}

export interface BacktestResult {
  run_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  strategy: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  final_balance: number;
  total_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  equity_curve: EquityPoint[];
  monthly_returns: Record<string, number>;
  trades: BacktestTrade[];
}

export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  side: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  drawdown_pct: number;
}

export interface PortfolioMetrics {
  total_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  current_drawdown_pct: number;
  profit_factor: number;
  win_rate: number;
  total_trades: number;
  avg_trade_duration_hours: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  expectancy: number;
  recovery_factor: number;
}

export interface AISignal {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  strategy: string;
  reasoning: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward: number;
  agents: AgentSignal[];
  created_at: string;
  expires_at: string;
}

export interface AgentSignal {
  agent_name: string;
  signal: 'BUY' | 'SELL' | 'HOLD' | 'NEUTRAL';
  confidence: number;
  weight: number;
  reasoning?: string;
}
