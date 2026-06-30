'use client';
import { useState, useEffect } from 'react';
import { Bell, CheckCircle2, XCircle, AlertTriangle, Info, TrendingUp, TrendingDown, Shield } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { formatDateTime } from '@/lib/utils/formatters';
import { getAlertColor } from '@/lib/utils/colors';
import type { RiskAlert } from '@/types/market';

const MOCK_ACTIVITY = [
  { id: '1', type: 'info' as const, title: 'London session opened', description: 'Liquidity conditions optimal for EURUSD', time: new Date(Date.now() - 5 * 60 * 1000).toISOString() },
  { id: '2', type: 'trade' as const, title: 'Position closed: EURUSD', description: 'Profit: +$142.50 (0.26%)', time: new Date(Date.now() - 15 * 60 * 1000).toISOString() },
  { id: '3', type: 'ai' as const, title: 'AI Signal generated: BUY GBPUSD', description: 'Confidence: 78% | R:R: 2.1', time: new Date(Date.now() - 22 * 60 * 1000).toISOString() },
  { id: '4', type: 'warning' as const, title: 'Exposure approaching limit', description: 'Total exposure at 14.2% (limit: 15%)', time: new Date(Date.now() - 45 * 60 * 1000).toISOString() },
  { id: '5', type: 'success' as const, title: 'Backtest completed', description: 'ICT_Momentum on EURUSD H1: +48.7% return', time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString() },
  { id: '6', type: 'error' as const, title: 'Order rejected: USDJPY', description: 'Insufficient margin', time: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString() },
];

interface ActivityItem {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error' | 'trade' | 'ai' | 'risk';
  title: string;
  description: string;
  time: string;
}

function ActivityIcon({ type }: { type: ActivityItem['type'] }) {
  switch (type) {
    case 'success':
      return <CheckCircle2 className="w-4 h-4 text-profit" />;
    case 'error':
      return <XCircle className="w-4 h-4 text-loss" />;
    case 'warning':
      return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
    case 'trade':
      return <TrendingUp className="w-4 h-4 text-primary" />;
    case 'ai':
      return <Shield className="w-4 h-4 text-purple-400" />;
    case 'risk':
      return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
    default:
      return <Info className="w-4 h-4 text-muted-foreground" />;
  }
}

export function ActivityFeed() {
  const [items] = useState<ActivityItem[]>(MOCK_ACTIVITY);
  const [filter, setFilter] = useState<string>('all');

  const filtered = filter === 'all' ? items : items.filter((i) => i.type === filter);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold text-foreground">Activity</h3>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">{filtered.length} events</span>
      </div>

      <div className="flex items-center gap-1 mb-2">
        {(['all', 'trade', 'ai', 'risk', 'system'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              'px-2 py-1 rounded text-[10px] font-medium transition-colors capitalize',
              filter === f ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            )}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hidden space-y-2" style={{ maxHeight: '280px' }}>
        {filtered.map((item) => (
          <div
            key={item.id}
            className="flex items-start gap-3 p-2.5 rounded-lg bg-muted/20 border border-border/30 hover:border-border/60 transition-colors"
          >
            <div className="flex-shrink-0 mt-0.5">
              <ActivityIcon type={item.type} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-foreground truncate">{item.title}</p>
                <span className="text-[10px] text-muted-foreground font-mono flex-shrink-0">
                  {formatDateTime(item.time)}
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{item.description}</p>
            </div>
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="text-center py-6 text-xs text-muted-foreground">
            No activity for this filter
          </div>
        )}
      </div>
    </div>
  );
}
