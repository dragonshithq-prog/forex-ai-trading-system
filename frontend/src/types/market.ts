// Market data types

export type Timeframe = 'M1' | 'M5' | 'M15' | 'M30' | 'H1' | 'H4' | 'D1' | 'W1';

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timeframe?: string;
}

export interface Tick {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
  mid?: number;
}

export type SessionName = 'Sydney' | 'Tokyo' | 'London' | 'New York';

export interface SessionInfo {
  active_session: string;
  sessions_active: string[];
  is_overlap: boolean;
  session_strength: number;
  time_to_next_session_minutes?: number;
  sessions: {
    sydney: SessionStatus;
    tokyo: SessionStatus;
    london: SessionStatus;
    new_york: SessionStatus;
  };
}

export interface SessionStatus {
  name: SessionName;
  is_open: boolean;
  open_time: string; // HH:mm UTC
  close_time: string; // HH:mm UTC
  local_time?: string;
  minutes_until_open?: number;
  minutes_until_close?: number;
}

export interface MarketStructure {
  symbol: string;
  timeframe: string;
  trend_direction: 'bullish' | 'bearish' | 'ranging';
  support_levels: number[];
  resistance_levels: number[];
  order_blocks: OrderBlock[];
  fair_value_gaps: FairValueGap[];
}

export interface OrderBlock {
  type: 'bullish' | 'bearish';
  high: number;
  low: number;
  timestamp: string;
  strength: number;
}

export interface FairValueGap {
  type: 'bullish' | 'bearish';
  high: number;
  low: number;
  timestamp: string;
  filled: boolean;
}

export interface CurrencyStrength {
  currency: string;
  strength_score: number;
  rank: number;
  pairs_analyzed: number;
  timestamp: string;
}

export interface RiskState {
  id?: string;
  broker_account_id?: string;
  current_equity: number;
  peak_equity: number;
  current_drawdown_pct: number;
  max_drawdown_pct: number;
  daily_pnl: number;
  weekly_pnl: number;
  monthly_pnl: number;
  total_exposure_pct: number;
  open_positions: number;
  consecutive_losses: number;
  daily_trades: number;
  is_circuit_breaker_active: boolean;
  circuit_breaker_until?: string;
  circuit_breaker_reason?: string;
  last_updated: string;
  last_trade_at?: string;
}

export interface RiskAlert {
  id: string;
  level: 'info' | 'warning' | 'critical' | 'emergency';
  category: string;
  message: string;
  current_value?: number;
  threshold_value?: number;
  action_required: boolean;
  acknowledged: boolean;
  created_at: string;
}

export interface RiskConfig {
  id?: string;
  max_position_size_pct: number;
  max_total_exposure_pct: number;
  max_positions: number;
  daily_drawdown_limit_pct: number;
  weekly_drawdown_limit_pct: number;
  monthly_drawdown_limit_pct: number;
  max_drawdown_limit_pct: number;
  max_exposure_per_pair_pct: number;
  max_correlated_exposure_pct: number;
  max_slippage_pips: number;
  max_spread_pips: number;
  max_consecutive_losses: number;
  cooldown_minutes: number;
  risk_per_trade_pct: number;
}

export interface ExposureData {
  total_exposure_pct: number;
  long_exposure_pct: number;
  short_exposure_pct: number;
  exposure_by_symbol: Record<string, number>;
  exposure_by_currency: Record<string, number>;
}
