// Mock data for demo mode when backend is not connected
import type { Position, Order, TradeJournalEntry, AccountSummary } from '@/types/trading';
import type { Candle, Tick, SessionInfo, RiskState, RiskAlert, RiskConfig, ExposureData } from '@/types/market';
import type { PortfolioMetrics, EquityPoint, AISignal, AgentSignal } from '@/types/api';

export const MOCK_ACCOUNT: AccountSummary = {
  account_id: 'ACC001',
  balance: 125_430.50,
  equity: 126_842.30,
  margin_used: 8_420.00,
  margin_available: 118_422.30,
  unrealized_pnl: 1_411.80,
  day_pnl: 2_340.50,
  day_pnl_pct: 1.87,
  currency: 'USD',
  leverage: 50,
};

export const MOCK_POSITIONS: Position[] = [
  {
    position_id: 'POS001',
    symbol: 'EURUSD',
    side: 'buy',
    size: 0.5,
    entry_price: 1.08234,
    current_price: 1.08512,
    unrealized_pnl: 139.0,
    unrealized_pnl_pct: 0.26,
    pips: 27.8,
    stop_loss: 1.07900,
    take_profit: 1.09100,
    strategy: 'ICT_Momentum',
    commission: 3.5,
    swap: -1.2,
    opened_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    status: 'open',
  },
  {
    position_id: 'POS002',
    symbol: 'GBPJPY',
    side: 'sell',
    size: 0.3,
    entry_price: 185.420,
    current_price: 184.890,
    unrealized_pnl: 144.23,
    unrealized_pnl_pct: 0.29,
    pips: 53.0,
    stop_loss: 186.200,
    take_profit: 183.500,
    strategy: 'Mean_Reversion',
    commission: 2.1,
    swap: 2.4,
    opened_at: new Date(Date.now() - 7.5 * 60 * 60 * 1000).toISOString(),
    status: 'open',
  },
  {
    position_id: 'POS003',
    symbol: 'USDJPY',
    side: 'buy',
    size: 1.0,
    entry_price: 149.245,
    current_price: 149.180,
    unrealized_pnl: -48.57,
    unrealized_pnl_pct: -0.04,
    pips: -6.5,
    stop_loss: 148.800,
    take_profit: 150.200,
    strategy: 'Breakout',
    commission: 7.0,
    swap: 4.8,
    opened_at: new Date(Date.now() - 1.5 * 60 * 60 * 1000).toISOString(),
    status: 'open',
  },
  {
    position_id: 'POS004',
    symbol: 'AUDUSD',
    side: 'sell',
    size: 0.8,
    entry_price: 0.65432,
    current_price: 0.65123,
    unrealized_pnl: 247.20,
    unrealized_pnl_pct: 0.47,
    pips: 30.9,
    stop_loss: 0.65800,
    take_profit: 0.64200,
    strategy: 'Trend_Following',
    commission: 5.6,
    swap: -0.8,
    opened_at: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
    status: 'open',
  },
];

export const MOCK_ORDERS: Order[] = [
  {
    id: 'ORD001',
    symbol: 'EURUSD',
    side: 'buy',
    order_type: 'market',
    quantity: 0.5,
    filled_quantity: 0.5,
    filled_price: 1.08234,
    status: 'filled',
    commission: 3.5,
    slippage: 0.1,
    filled_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'ORD002',
    symbol: 'GBPJPY',
    side: 'sell',
    order_type: 'market',
    quantity: 0.3,
    filled_quantity: 0.3,
    filled_price: 185.420,
    status: 'filled',
    commission: 2.1,
    slippage: 0.2,
    filled_at: new Date(Date.now() - 7.5 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 7.5 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'ORD003',
    symbol: 'EURJPY',
    side: 'buy',
    order_type: 'limit',
    quantity: 0.4,
    price: 160.500,
    filled_quantity: 0,
    status: 'open',
    commission: 0,
    slippage: 0,
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  },
  {
    id: 'ORD004',
    symbol: 'NZDUSD',
    side: 'sell',
    order_type: 'market',
    quantity: 0.6,
    filled_quantity: 0.6,
    filled_price: 0.60123,
    status: 'filled',
    commission: 4.2,
    slippage: 0.1,
    filled_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
  },
];

export const MOCK_AI_SIGNAL: AISignal = {
  id: 'SIG001',
  symbol: 'EURUSD',
  direction: 'BUY',
  confidence: 0.82,
  strategy: 'ICT_Momentum',
  reasoning: 'Market structure shows bullish BOS on H4. Price has returned to the OB at 1.0823 with confluence from the London session open. London/NY overlap provides high liquidity conditions. FVG from yesterday\'s session still unfilled.',
  entry_price: 1.08234,
  stop_loss: 1.07900,
  take_profit: 1.09100,
  risk_reward: 2.54,
  agents: [
    {
      agent_name: 'Structure Agent',
      signal: 'BUY',
      confidence: 0.88,
      weight: 0.25,
      reasoning: 'Clean HH/HL structure on H4',
    },
    {
      agent_name: 'ICT Agent',
      signal: 'BUY',
      confidence: 0.85,
      weight: 0.25,
      reasoning: 'Price at bullish OB, FVG above',
    },
    {
      agent_name: 'Sentiment Agent',
      signal: 'BUY',
      confidence: 0.75,
      weight: 0.20,
      reasoning: 'EUR sentiment improving vs USD',
    },
    {
      agent_name: 'Session Agent',
      signal: 'BUY',
      confidence: 0.90,
      weight: 0.15,
      reasoning: 'London session optimal for EURUSD',
    },
    {
      agent_name: 'Risk Agent',
      signal: 'HOLD',
      confidence: 0.60,
      weight: 0.15,
      reasoning: 'Already holding correlated position',
    },
  ],
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  expires_at: new Date(Date.now() + 55 * 60 * 1000).toISOString(),
};

export const MOCK_SESSION_INFO: SessionInfo = {
  active_session: 'London/New York',
  sessions_active: ['London', 'New York'],
  is_overlap: true,
  session_strength: 0.92,
  time_to_next_session_minutes: 180,
  sessions: {
    sydney: {
      name: 'Sydney',
      is_open: false,
      open_time: '22:00',
      close_time: '07:00',
      minutes_until_open: 420,
      minutes_until_close: 0,
    },
    tokyo: {
      name: 'Tokyo',
      is_open: false,
      open_time: '00:00',
      close_time: '09:00',
      minutes_until_open: 300,
      minutes_until_close: 0,
    },
    london: {
      name: 'London',
      is_open: true,
      open_time: '08:00',
      close_time: '17:00',
      minutes_until_open: 0,
      minutes_until_close: 180,
    },
    new_york: {
      name: 'New York',
      is_open: true,
      open_time: '13:00',
      close_time: '22:00',
      minutes_until_open: 0,
      minutes_until_close: 360,
    },
  },
};

export const MOCK_RISK_STATE: RiskState = {
  current_equity: 126_842.30,
  peak_equity: 130_120.00,
  current_drawdown_pct: 2.52,
  max_drawdown_pct: 4.87,
  daily_pnl: 2_340.50,
  weekly_pnl: 5_820.30,
  monthly_pnl: 12_450.80,
  total_exposure_pct: 14.2,
  open_positions: 4,
  consecutive_losses: 0,
  daily_trades: 6,
  is_circuit_breaker_active: false,
  last_updated: new Date().toISOString(),
};

export const MOCK_RISK_ALERTS: RiskAlert[] = [
  {
    id: 'ALT001',
    level: 'warning',
    category: 'exposure',
    message: 'Total exposure approaching 15% limit (currently 14.2%)',
    current_value: 14.2,
    threshold_value: 15.0,
    action_required: false,
    acknowledged: false,
    created_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
  },
];

export const MOCK_RISK_CONFIG: RiskConfig = {
  max_position_size_pct: 2.0,
  max_total_exposure_pct: 15.0,
  max_positions: 10,
  daily_drawdown_limit_pct: 3.0,
  weekly_drawdown_limit_pct: 7.0,
  monthly_drawdown_limit_pct: 15.0,
  max_drawdown_limit_pct: 15.0,
  max_exposure_per_pair_pct: 5.0,
  max_correlated_exposure_pct: 10.0,
  max_slippage_pips: 3.0,
  max_spread_pips: 5.0,
  max_consecutive_losses: 5,
  cooldown_minutes: 60,
  risk_per_trade_pct: 1.0,
};

export const MOCK_EXPOSURE: ExposureData = {
  total_exposure_pct: 14.2,
  long_exposure_pct: 9.1,
  short_exposure_pct: 5.1,
  exposure_by_symbol: {
    EURUSD: 3.8,
    GBPJPY: 2.1,
    USDJPY: 5.6,
    AUDUSD: 2.7,
  },
  exposure_by_currency: {
    EUR: 3.8,
    GBP: 2.1,
    USD: 9.4,
    JPY: 7.7,
    AUD: 2.7,
  },
};

export const MOCK_PORTFOLIO_METRICS: PortfolioMetrics = {
  total_return_pct: 24.87,
  sharpe_ratio: 2.14,
  sortino_ratio: 3.22,
  calmar_ratio: 5.11,
  max_drawdown_pct: 4.87,
  current_drawdown_pct: 2.52,
  profit_factor: 2.34,
  win_rate: 67.4,
  total_trades: 312,
  avg_trade_duration_hours: 6.4,
  best_trade_pct: 3.82,
  worst_trade_pct: -1.24,
  avg_win_pct: 1.42,
  avg_loss_pct: -0.61,
  expectancy: 0.68,
  recovery_factor: 5.11,
};

// Generate mock equity curve
export function generateMockEquityCurve(days = 90): EquityPoint[] {
  const points: EquityPoint[] = [];
  let equity = 100_000;
  let peak = equity;
  const now = Date.now();

  for (let i = days; i >= 0; i--) {
    const ts = new Date(now - i * 24 * 60 * 60 * 1000).toISOString();
    const change = (Math.random() - 0.4) * 800;
    equity = Math.max(equity + change, 90_000);
    peak = Math.max(peak, equity);
    const drawdown = ((peak - equity) / peak) * 100;
    points.push({ timestamp: ts, equity, drawdown_pct: drawdown });
  }
  return points;
}

// Generate mock candles
export function generateMockCandles(count = 200, symbol = 'EURUSD'): Candle[] {
  const candles: Candle[] = [];
  const isJpy = symbol.includes('JPY');
  let price = isJpy ? 149.5 : 1.0823;
  const volatility = isJpy ? 0.3 : 0.0015;
  const now = Date.now();

  for (let i = count; i >= 0; i--) {
    const ts = new Date(now - i * 60 * 60 * 1000).toISOString();
    const open = price;
    const change = (Math.random() - 0.5) * volatility * 2;
    const close = price + change;
    const high = Math.max(open, close) + Math.random() * volatility;
    const low = Math.min(open, close) - Math.random() * volatility;
    const volume = Math.random() * 1000 + 500;

    candles.push({ timestamp: ts, open, high, low, close, volume });
    price = close;
  }
  return candles;
}

// Generate mock monthly returns
export function generateMockMonthlyReturns(): Record<string, number> {
  const result: Record<string, number> = {};
  const now = new Date();

  for (let y = 0; y < 2; y++) {
    for (let m = 0; m < 12; m++) {
      const year = now.getFullYear() - y;
      const month = m + 1;
      if (year === now.getFullYear() && month > now.getMonth() + 1) continue;
      const key = `${year}-${String(month).padStart(2, '0')}`;
      result[key] = (Math.random() - 0.35) * 8;
    }
  }
  return result;
}

export const MOCK_JOURNAL_ENTRIES: TradeJournalEntry[] = [
  {
    id: 'JRN001',
    position_id: 'POS001',
    symbol: 'EURUSD',
    side: 'buy',
    entry_price: 1.08234,
    strategy: 'ICT_Momentum',
    notes: 'Clean BOS on H4, price returned to OB. Executed at London open with tight spread.',
    tags: ['ICT', 'London', 'BOS', 'OB'],
    rating: 4,
    setup: 'Bullish BOS + OB retest',
    entry_reason: 'Price reacted to the 4H bullish OB with confirmation candle',
    opened_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'JRN002',
    symbol: 'GBPUSD',
    side: 'sell',
    entry_price: 1.26540,
    exit_price: 1.25980,
    pnl: 336.0,
    pnl_pct: 0.44,
    strategy: 'Mean_Reversion',
    notes: 'Good trade, respected the resistance zone.',
    tags: ['Resistance', 'London'],
    rating: 5,
    setup: 'Strong resistance + bearish engulfing',
    entry_reason: 'Multiple failed attempts to break resistance',
    exit_reason: 'Reached TP1',
    opened_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    closed_at: new Date(Date.now() - 1.5 * 24 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  },
];
