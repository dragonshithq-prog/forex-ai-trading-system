// Formatting utilities for trading data

/**
 * Format a currency value with symbol and locale formatting
 */
export function formatCurrency(
  value: number,
  currency = 'USD',
  minimumFractionDigits = 2,
  maximumFractionDigits = 2
): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

/**
 * Format a number with fixed decimal places (monospace-friendly)
 */
export function formatNumber(
  value: number,
  decimals = 2,
  forceSign = false
): string {
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(value));

  if (forceSign) {
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  }
  return value < 0 ? `-${formatted}` : formatted;
}

/**
 * Format a percentage value
 */
export function formatPercent(
  value: number,
  decimals = 2,
  forceSign = false
): string {
  const abs = Math.abs(value);
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(abs);

  if (forceSign) {
    return value >= 0 ? `+${formatted}%` : `-${formatted}%`;
  }
  return value < 0 ? `-${formatted}%` : `${formatted}%`;
}

/**
 * Format pip value (5-decimal for JPY pairs, else 4-decimal)
 */
export function formatPips(pips: number, symbol?: string): string {
  const isJpy = symbol?.includes('JPY');
  const formatted = formatNumber(pips, isJpy ? 2 : 1, true);
  return `${formatted} pips`;
}

/**
 * Calculate pips from price difference
 */
export function calculatePips(
  entryPrice: number,
  currentPrice: number,
  symbol: string,
  side: string
): number {
  const isJpy = symbol.includes('JPY');
  const pipSize = isJpy ? 0.01 : 0.0001;
  const diff = side.toUpperCase() === 'BUY'
    ? currentPrice - entryPrice
    : entryPrice - currentPrice;
  return diff / pipSize;
}

/**
 * Format price with correct decimal places for the symbol
 */
export function formatPrice(price: number, symbol?: string): string {
  const isJpy = symbol?.includes('JPY');
  const decimals = isJpy ? 3 : 5;
  return price.toFixed(decimals);
}

/**
 * Format a duration in human-readable form
 */
export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

/**
 * Format duration from an open time string
 */
export function formatPositionDuration(openedAt: string): string {
  const ms = Date.now() - new Date(openedAt).getTime();
  return formatDuration(ms);
}

/**
 * Format a date/time for display
 */
export function formatDateTime(dateStr: string, includeSeconds = false): string {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
    hour12: false,
  }).format(date);
}

/**
 * Format a date only
 */
export function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(dateStr));
}

/**
 * Format a time only (UTC)
 */
export function formatTimeUTC(dateStr: string): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(dateStr));
}

/**
 * Format a lot size
 */
export function formatLotSize(size: number): string {
  if (size >= 1) return size.toFixed(2);
  return size.toFixed(4);
}

/**
 * Abbreviate large numbers
 */
export function abbreviateNumber(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(2);
}

/**
 * Format P&L with sign and currency
 */
export function formatPnL(value: number, currency = 'USD'): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${formatCurrency(value, currency)}`;
}

/**
 * Get month/year label from ISO string
 */
export function formatSpread(spread: number, isJpy?: boolean): string {
  const pips = isJpy ? spread * 100 : spread * 10000;
  return `${pips.toFixed(1)}`;
}

export function getMonthYear(dateStr: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    year: '2-digit',
  }).format(new Date(dateStr));
}
