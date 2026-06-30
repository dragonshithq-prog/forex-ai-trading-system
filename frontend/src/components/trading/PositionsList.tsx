'use client';
import { AnimatePresence } from 'framer-motion';
import { TrendingUp, Inbox } from 'lucide-react';
import { PositionCard } from './PositionCard';
import { usePositions } from '@/lib/hooks/usePositions';
import { useTradingStore } from '@/lib/store/tradingStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { formatPnL } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';

interface PositionsListProps {
  compact?: boolean;
  maxHeight?: string;
}

export function PositionsList({ compact = false, maxHeight = '400px' }: PositionsListProps) {
  const { positions, isLoading, refresh } = usePositions();
  const removePosition = useTradingStore((s) => s.removePosition);

  const totalPnL = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);

  const handleClose = (id: string) => {
    removePosition(id);
    refresh();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-1 mb-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold text-foreground">Open Positions</h3>
          {positions.length > 0 && (
            <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-mono">
              {positions.length}
            </span>
          )}
        </div>
        {positions.length > 0 && (
          <div className={cn('text-sm font-mono font-semibold tabular-nums', getPnLColor(totalPnL))}>
            {formatPnL(totalPnL)}
          </div>
        )}
      </div>

      {/* Positions list */}
      <div
        className="flex-1 overflow-y-auto space-y-2 scrollbar-hidden"
        style={{ maxHeight }}
        role="list"
        aria-label="Open positions"
        aria-live="polite"
        aria-busy={isLoading}
      >
        {isLoading && positions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <LoadingSpinner size="sm" label="Loading positions..." />
          </div>
        ) : positions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
              <Inbox className="w-5 h-5 text-muted-foreground" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">No open positions</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Positions will appear here when trades are opened
              </p>
            </div>
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {positions.map((position) => (
              <div key={position.position_id} role="listitem">
                <PositionCard
                  position={position}
                  onClose={handleClose}
                  compact={compact}
                />
              </div>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
