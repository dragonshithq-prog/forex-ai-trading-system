'use client';
import { BookOpen, Star, Tag, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { Badge } from '@/components/common/Badge';
import { formatDate, formatPnL, formatPrice } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import type { TradeJournalEntry } from '@/types/trading';

interface TradeJournalProps {
  entries: TradeJournalEntry[];
  isLoading?: boolean;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5" aria-label={`Rating: ${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          className={cn(
            'w-3 h-3',
            star <= rating ? 'text-yellow-400 fill-yellow-400' : 'text-muted'
          )}
          aria-hidden
        />
      ))}
    </div>
  );
}

export function TradeJournal({ entries, isLoading }: TradeJournalProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 bg-muted/20 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  if (!entries.length) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center gap-3">
        <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-muted-foreground" aria-hidden />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">No journal entries</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Closed trades will appear here automatically
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3" role="list" aria-label="Trade journal entries">
      {entries.map((entry) => {
        const isBuy = entry.side.toUpperCase() === 'BUY';
        const isOpen = !entry.closed_at;

        return (
          <div
            key={entry.id}
            role="listitem"
            className="bg-card border border-border rounded-lg p-4 hover:border-border/60 transition-colors"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                {isBuy ? (
                  <TrendingUp className="w-4 h-4 text-buy" aria-hidden />
                ) : (
                  <TrendingDown className="w-4 h-4 text-sell" aria-hidden />
                )}
                <span className="font-semibold text-sm font-mono text-foreground">
                  {entry.symbol}
                </span>
                <Badge variant={isBuy ? 'buy' : 'sell'} size="sm">
                  {entry.side.toUpperCase()}
                </Badge>
                {isOpen && <Badge variant="warning" size="sm" dot>Open</Badge>}
                {entry.strategy && (
                  <span className="text-[10px] text-muted-foreground">{entry.strategy}</span>
                )}
              </div>

              <div className="flex items-center gap-3">
                {entry.rating && <StarRating rating={entry.rating} />}
                {entry.pnl !== undefined && (
                  <span className={cn('text-sm font-mono font-semibold tabular-nums', getPnLColor(entry.pnl))}>
                    {formatPnL(entry.pnl)}
                  </span>
                )}
              </div>
            </div>

            {/* Price info */}
            <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono mb-2">
              <span>Entry: {formatPrice(entry.entry_price, entry.symbol)}</span>
              {entry.exit_price && (
                <span>Exit: {formatPrice(entry.exit_price, entry.symbol)}</span>
              )}
              <span>{formatDate(entry.opened_at)}</span>
            </div>

            {/* Notes */}
            {entry.notes && (
              <p className="text-xs text-muted-foreground bg-muted/30 rounded px-2.5 py-2 mb-2">
                {entry.notes}
              </p>
            )}

            {/* Tags */}
            {entry.tags && entry.tags.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap">
                <Tag className="w-3 h-3 text-muted-foreground/50" aria-hidden />
                {entry.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
