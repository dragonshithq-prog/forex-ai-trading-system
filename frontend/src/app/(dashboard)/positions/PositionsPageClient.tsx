'use client';
import { PositionsList } from '@/components/trading/PositionsList';
import { OrderForm } from '@/components/trading/OrderForm';
import { usePositions } from '@/lib/hooks/usePositions';
import { formatCurrency, formatPnL } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';

export function PositionsPageClient() {
  const { positions, refresh } = usePositions();
  const totalPnL = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const totalSize = positions.reduce((s, p) => s + p.size, 0);

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Positions</h1>
          <p className="text-sm text-muted-foreground">Manage your open trading positions</p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">Total Unrealized P&L</div>
            <div className={cn('font-mono font-bold tabular-nums text-lg', getPnLColor(totalPnL))}>
              {formatPnL(totalPnL)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-muted-foreground">Open Positions</div>
            <div className="font-mono font-bold text-foreground text-lg">
              {positions.length}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Positions list */}
        <div className="lg:col-span-2 bg-card border border-border rounded-lg p-4">
          <PositionsList maxHeight="600px" />
        </div>

        {/* Order form */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-4">Place Order</h2>
          <OrderForm onSuccess={() => setTimeout(refresh, 1000)} />
        </div>
      </div>
    </div>
  );
}
