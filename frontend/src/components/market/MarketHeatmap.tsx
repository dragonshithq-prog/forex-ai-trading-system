'use client';
import { useMemo } from 'react';
import { cn } from '@/lib/utils/cn';
import { useMarketStore } from '@/lib/store/marketStore';

const PAIRS = [
  { symbol: 'EURUSD', group: 'EUR' },
  { symbol: 'GBPUSD', group: 'GBP' },
  { symbol: 'USDJPY', group: 'JPY' },
  { symbol: 'AUDUSD', group: 'AUD' },
  { symbol: 'USDCAD', group: 'CAD' },
  { symbol: 'USDCHF', group: 'CHF' },
  { symbol: 'NZDUSD', group: 'NZD' },
  { symbol: 'EURJPY', group: 'EUR' },
  { symbol: 'GBPJPY', group: 'GBP' },
  { symbol: 'GBPCHF', group: 'GBP' },
  { symbol: 'EURAUD', group: 'EUR' },
  { symbol: 'GBPNZD', group: 'GBP' },
];

export function MarketHeatmap() {
  const ticks = useMarketStore((s) => s.ticks);

  const rows = useMemo(() => {
    return PAIRS.map((p) => {
      const tick = ticks[p.symbol];
      if (!tick) return null;
      const change = ((tick.bid - tick.bid) / tick.bid) * 100;
      const intensity = Math.min(Math.abs(change) / 0.5, 1);
      return {
        symbol: p.symbol,
        group: p.group,
        bid: tick.bid,
        change,
        intensity,
        isUp: change >= 0,
      };
    }).filter((r): r is NonNullable<typeof r> => r !== null);
  }, [ticks]);

  const maxIntensity = Math.max(...rows.map((r) => r.intensity), 0.01);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground">Market Heatmap</h3>
        <span className="text-[10px] text-muted-foreground font-mono">24h change</span>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {rows.map((row) => {
          const opacity = 0.3 + (row.intensity / maxIntensity) * 0.7;
          return (
            <div
              key={row.symbol}
              className={cn(
                'flex flex-col items-center justify-center p-2.5 rounded-lg border transition-all cursor-pointer hover:scale-105',
                row.isUp ? 'border-profit/20' : 'border-loss/20'
              )}
              style={{
                backgroundColor: row.isUp
                  ? `rgba(34, 197, 94, ${opacity * 0.15})`
                  : `rgba(239, 68, 68, ${opacity * 0.15})`,
              }}
            >
              <span className="text-xs font-bold font-mono text-foreground">{row.symbol}</span>
              <span className={cn('text-[10px] font-mono font-semibold mt-0.5 tabular-nums', row.isUp ? 'text-profit' : 'text-loss')}>
                {row.isUp ? '+' : ''}{row.change.toFixed(3)}%
              </span>
              <span className="text-[10px] font-mono text-muted-foreground mt-0.5">
                {row.bid.toFixed(row.symbol.includes('JPY') ? 3 : 5)}
              </span>
            </div>
          );
        })}

        {rows.length === 0 && (
          <div className="col-span-full text-center py-6 text-xs text-muted-foreground">
            Waiting for market data...
          </div>
        )}
      </div>
    </div>
  );
}
