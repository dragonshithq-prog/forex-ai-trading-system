'use client';
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, ChevronDown, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { Badge } from '@/components/common/Badge';
import { useMarketStore } from '@/lib/store/marketStore';
import {
  formatCurrency,
  formatPrice,
  formatPositionDuration,
  formatPnL,
  calculatePips,
} from '@/lib/utils/formatters';
import { getPnLColor, getSideBgColor } from '@/lib/utils/colors';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import type { Position } from '@/types/trading';

interface PositionCardProps {
  position: Position;
  onClose?: (id: string) => void;
  compact?: boolean;
}

export function PositionCard({ position, onClose, compact = false }: PositionCardProps) {
  const tick = useMarketStore((s) => s.ticks[position.symbol]);
  const [isClosing, setIsClosing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [prevPnl, setPrevPnl] = useState(position.unrealized_pnl);
  const [pnlFlash, setPnlFlash] = useState<'up' | 'down' | null>(null);

  // Live price from WebSocket or fallback to position data
  const currentPrice = tick?.bid ?? position.current_price;
  const pnl = position.unrealized_pnl;
  const pips = calculatePips(
    position.entry_price,
    currentPrice,
    position.symbol,
    position.side
  );

  // Flash animation on P&L change
  useEffect(() => {
    if (pnl !== prevPnl) {
      setPnlFlash(pnl > prevPnl ? 'up' : 'down');
      setPrevPnl(pnl);
      const t = setTimeout(() => setPnlFlash(null), 600);
      return () => clearTimeout(t);
    }
  }, [pnl, prevPnl]);

  const handleClose = async () => {
    setIsClosing(true);
    try {
      await api.trading.closePosition(position.position_id, { partial_pct: 100 });
      toast.success(`Position ${position.symbol} closed`);
      onClose?.(position.position_id);
    } catch (err) {
      toast.error('Failed to close position. Please try again.');
    } finally {
      setIsClosing(false);
    }
  };

  const isBuy = position.side.toUpperCase() === 'BUY';
  const SideIcon = isBuy ? TrendingUp : TrendingDown;
  const isJpy = position.symbol.includes('JPY');

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.15 }}
      className="bg-card border border-border rounded-lg overflow-hidden hover:border-border/60 transition-colors"
    >
      {/* Main row */}
      <div className={cn('flex items-center gap-3 px-3', compact ? 'py-2' : 'py-3')}>
        {/* Symbol + side */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <SideIcon
            className={cn('w-4 h-4 flex-shrink-0', isBuy ? 'text-buy' : 'text-sell')}
            aria-hidden
          />
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold text-foreground font-mono">
                {position.symbol}
              </span>
              <Badge variant={isBuy ? 'buy' : 'sell'} size="sm">
                {position.side.toUpperCase()}
              </Badge>
            </div>
            {!compact && (
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-muted-foreground font-mono">
                  {position.size} lot{position.size !== 1 ? 's' : ''}
                </span>
                {position.strategy && (
                  <span className="text-[10px] text-muted-foreground/70">
                    {position.strategy}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Entry → Current */}
        <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-muted-foreground tabular-nums">
          <span>{formatPrice(position.entry_price, position.symbol)}</span>
          <span className="text-border">→</span>
          <span className={cn('font-medium', pnl >= 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {formatPrice(currentPrice, position.symbol)}
          </span>
        </div>

        {/* Pips */}
        <div className="hidden md:block text-xs font-mono tabular-nums">
          <span className={cn(pips >= 0 ? 'text-profit' : 'text-loss')}>
            {pips >= 0 ? '+' : ''}{pips.toFixed(1)}p
          </span>
        </div>

        {/* P&L */}
        <div
          className={cn(
            'text-right min-w-[80px] font-mono tabular-nums transition-colors duration-300',
            pnlFlash === 'up' ? 'text-profit' : pnlFlash === 'down' ? 'text-loss' : getPnLColor(pnl)
          )}
        >
          <div className="text-sm font-semibold">{formatPnL(pnl)}</div>
          {!compact && (
            <div className="text-[10px] text-muted-foreground">
              {position.unrealized_pnl_pct !== undefined
                ? `${pnl >= 0 ? '+' : ''}${position.unrealized_pnl_pct.toFixed(2)}%`
                : ''}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {!compact && (
            <button
              onClick={() => setShowDetails((s) => !s)}
              className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={showDetails ? 'Hide details' : 'Show details'}
              aria-expanded={showDetails}
            >
              <ChevronDown
                className={cn('w-3 h-3 transition-transform', showDetails ? 'rotate-180' : '')}
                aria-hidden
              />
            </button>
          )}

          <button
            onClick={handleClose}
            disabled={isClosing}
            className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-loss hover:bg-loss/10 transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`Close ${position.symbol} position`}
          >
            {isClosing ? (
              <div className="w-3 h-3 border-2 border-muted border-t-foreground rounded-full animate-spin" aria-hidden />
            ) : (
              <X className="w-3 h-3" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {showDetails && !compact && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.15 }}
          className="px-3 pb-3 border-t border-border/50"
        >
          <div className="grid grid-cols-3 gap-3 mt-3 text-xs">
            <div>
              <div className="text-muted-foreground mb-0.5">Stop Loss</div>
              <div className="font-mono text-foreground tabular-nums">
                {position.stop_loss
                  ? formatPrice(position.stop_loss, position.symbol)
                  : '—'}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground mb-0.5">Take Profit</div>
              <div className="font-mono text-foreground tabular-nums">
                {position.take_profit
                  ? formatPrice(position.take_profit, position.symbol)
                  : '—'}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground mb-0.5">Duration</div>
              <div className="font-mono text-foreground">
                {formatPositionDuration(position.opened_at)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground mb-0.5">Commission</div>
              <div className="font-mono text-foreground tabular-nums">
                {formatCurrency(-(position.commission ?? 0))}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground mb-0.5">Swap</div>
              <div className={cn('font-mono tabular-nums', getPnLColor(position.swap ?? 0))}>
                {formatPnL(position.swap ?? 0)}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground mb-0.5">Net P&L</div>
              <div className={cn('font-mono font-semibold tabular-nums', getPnLColor(pnl))}>
                {formatPnL(pnl - (position.commission ?? 0) + (position.swap ?? 0))}
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}
