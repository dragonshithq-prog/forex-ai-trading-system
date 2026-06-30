// Color helpers for trading UI

/**
 * Returns Tailwind class for profit/loss coloring
 */
export function getPnLColor(value: number): string {
  if (value > 0) return 'text-profit';
  if (value < 0) return 'text-loss';
  return 'text-muted-foreground';
}

/**
 * Returns Tailwind bg class for profit/loss
 */
export function getPnLBgColor(value: number): string {
  if (value > 0) return 'bg-profit/10';
  if (value < 0) return 'bg-loss/10';
  return 'bg-muted/10';
}

/**
 * Returns color for trade side (buy/sell)
 */
export function getSideColor(side: string): string {
  const normalized = side.toUpperCase();
  if (normalized === 'BUY' || normalized === 'LONG') return 'text-buy';
  if (normalized === 'SELL' || normalized === 'SHORT') return 'text-sell';
  return 'text-muted-foreground';
}

/**
 * Returns background color for trade side
 */
export function getSideBgColor(side: string): string {
  const normalized = side.toUpperCase();
  if (normalized === 'BUY' || normalized === 'LONG') return 'bg-buy/15 text-buy';
  if (normalized === 'SELL' || normalized === 'SHORT') return 'bg-sell/15 text-sell';
  return 'bg-muted text-muted-foreground';
}

/**
 * Returns color for risk alert level
 */
export function getAlertColor(level: string): string {
  switch (level.toLowerCase()) {
    case 'emergency':
      return 'text-red-500';
    case 'critical':
      return 'text-orange-500';
    case 'warning':
      return 'text-yellow-500';
    case 'info':
      return 'text-blue-400';
    default:
      return 'text-muted-foreground';
  }
}

/**
 * Returns color class for confidence level
 */
export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-profit';
  if (confidence >= 0.6) return 'text-yellow-400';
  return 'text-loss';
}

/**
 * Returns hex color for chart line (not token, used for canvas elements)
 */
export const CHART_COLORS = {
  profit: '#22c55e',
  loss: '#ef4444',
  buy: '#3b82f6',
  sell: '#f97316',
  neutral: '#6b7280',
  ema20: '#f59e0b',
  ema50: '#8b5cf6',
  ema200: '#ec4899',
  volume: 'rgba(59, 130, 246, 0.4)',
  background: '#0a0a0a',
  surface: '#111111',
  border: '#222222',
  text: '#a1a1aa',
  grid: '#1c1c1c',
} as const;

/**
 * Interpolates between red and green based on value (0-1)
 */
export function getGradientColor(value: number): string {
  // 0 = red, 0.5 = neutral, 1 = green
  const r = value < 0.5 ? 255 : Math.round(255 * (1 - value) * 2);
  const g = value > 0.5 ? 220 : Math.round(220 * value * 2);
  return `rgb(${r}, ${g}, 50)`;
}

/**
 * Returns drawdown severity color
 */
export function getDrawdownColor(drawdownPct: number): string {
  if (drawdownPct >= 15) return 'text-red-500';
  if (drawdownPct >= 10) return 'text-orange-500';
  if (drawdownPct >= 5) return 'text-yellow-500';
  return 'text-profit';
}

/**
 * Session color map
 */
export const SESSION_COLORS = {
  Sydney: { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/30', dot: '#38bdf8' },
  Tokyo: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', dot: '#f87171' },
  London: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', dot: '#60a5fa' },
  'New York': { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', dot: '#c084fc' },
} as const;
