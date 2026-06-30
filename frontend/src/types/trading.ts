// Trading domain types

export type TradeSide = 'buy' | 'sell' | 'BUY' | 'SELL';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit';
export type OrderStatus = 'pending' | 'open' | 'filled' | 'partial' | 'cancelled' | 'rejected' | 'expired';
export type PositionStatus = 'open' | 'closed' | 'partial';

export interface Position {
  position_id: string;
  symbol: string;
  side: TradeSide;
  size: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  realized_pnl?: number;
  unrealized_pnl_pct?: number;
  pips?: number;
  stop_loss?: number;
  take_profit?: number;
  trailing_stop?: number;
  strategy?: string;
  commission?: number;
  swap?: number;
  opened_at: string;
  closed_at?: string;
  status?: PositionStatus;
  broker_position_id?: string;
}

export interface Order {
  id: string;
  symbol: string;
  side: TradeSide;
  order_type: OrderType;
  quantity: number;
  price?: number;
  stop_price?: number;
  take_profit?: number;
  stop_loss?: number;
  status: OrderStatus;
  filled_quantity: number;
  filled_price?: number;
  commission: number;
  slippage: number;
  rejection_reason?: string;
  submitted_at?: string;
  filled_at?: string;
  created_at: string;
}

export interface TradeJournalEntry {
  id: string;
  position_id?: string;
  symbol: string;
  side: TradeSide;
  entry_price: number;
  exit_price?: number;
  pnl?: number;
  pnl_pct?: number;
  strategy?: string;
  notes?: string;
  tags?: string[];
  rating?: number; // 1-5
  emotions?: string;
  setup?: string;
  entry_reason?: string;
  exit_reason?: string;
  screenshot_url?: string;
  opened_at: string;
  closed_at?: string;
  created_at: string;
}

export interface AccountSummary {
  account_id: string;
  balance: number;
  equity: number;
  margin_used: number;
  margin_available: number;
  unrealized_pnl: number;
  day_pnl: number;
  day_pnl_pct: number;
  currency: string;
  leverage: number;
}
