'use client';
import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Star, StarOff } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { useMarketStore } from '@/lib/store/marketStore';
import { formatPrice, formatSpread } from '@/lib/utils/formatters';

const DEFAULT_SYMBOLS = [
  { symbol: 'EURUSD', name: 'Euro / US Dollar', favorite: true },
  { symbol: 'GBPUSD', name: 'British Pound / US Dollar', favorite: true },
  { symbol: 'USDJPY', name: 'US Dollar / Japanese Yen', favorite: true },
  { symbol: 'GBPJPY', name: 'British Pound / Japanese Yen', favorite: false },
  { symbol: 'AUDUSD', name: 'Australian Dollar / US Dollar', favorite: false },
  { symbol: 'USDCAD', name: 'US Dollar / Canadian Dollar', favorite: false },
  { symbol: 'USDCHF', name: 'US Dollar / Swiss Franc', favorite: false },
  { symbol: 'NZDUSD', name: 'New Zealand Dollar / US Dollar', favorite: false },
  { symbol: 'EURJPY', name: 'Euro / Japanese Yen', favorite: false },
  { symbol: 'GBPCHF', name: 'British Pound / Swiss Franc', favorite: false },
];

interface WatchlistProps {
  onSymbolSelect?: (symbol: string) => void;
}

export function Watchlist({ onSymbolSelect }: WatchlistProps) {
  const ticks = useMarketStore((s) => s.ticks);
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS);
  const [filter, setFilter] = useState('');

  const toggleFavorite = (symbol: string) => {
    setSymbols((prev) =>
      prev.map((s) => (s.symbol === symbol ? { ...s, favorite: !s.favorite } : s))
    );
  };

  const filtered = symbols
    .filter((s) => s.favorite || !filter)
    .filter((s) => s.symbol.toLowerCase().includes(filter.toLowerCase()) || s.name.toLowerCase().includes(filter.toLowerCase()));

  const sorted = [...filtered].sort((a, b) => (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0));

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground">Watchlist</h3>
        <span className="text-[10px] text-muted-foreground font-mono">{sorted.length} pairs</span>
      </div>

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search symbols..."
        className="w-full bg-muted border border-border rounded-md px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring mb-2 font-mono"
      />

      <div className="flex-1 overflow-y-auto scrollbar-hidden space-y-0.5" style={{ maxHeight: '320px' }}>
        {sorted.map(({ symbol, name, favorite }) => {
          const tick = ticks[symbol];
          const isJpy = symbol.includes('JPY');
          const decimals = isJpy ? 3 : 5;

          return (
            <div
              key={symbol}
              className={cn(
                'flex items-center gap-2 px-2.5 py-2 rounded-md transition-colors cursor-pointer group',
                'hover:bg-muted/60 border border-transparent hover:border-border/50'
              )}
              onClick={() => onSymbolSelect?.(symbol)}
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleFavorite(symbol);
                }}
                className="flex-shrink-0 text-muted-foreground hover:text-yellow-400 transition-colors"
                aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
              >
                {favorite ? (
                  <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                ) : (
                  <StarOff className="w-3 h-3" />
                )}
              </button>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold font-mono text-foreground">{symbol}</span>
                  {tick ? (
                    <span className="text-xs font-mono font-semibold tabular-nums text-foreground">
                      {tick.bid.toFixed(decimals)}
                    </span>
                  ) : (
                    <span className="text-xs font-mono text-muted-foreground">—</span>
                  )}
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[10px] text-muted-foreground truncate">{name}</span>
                  {tick ? (
                    <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
                      Spr: {formatSpread(tick.spread, isJpy)}
                    </span>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}

        {sorted.length === 0 && (
          <div className="text-center py-6 text-xs text-muted-foreground">
            No symbols match your filter
          </div>
        )}
      </div>
    </div>
  );
}
