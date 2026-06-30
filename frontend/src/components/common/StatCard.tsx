import { cn } from '@/lib/utils/cn';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string;
  subValue?: string;
  trend?: number; // positive = up, negative = down, undefined = neutral
  trendLabel?: string;
  icon?: LucideIcon;
  iconColor?: string;
  isLoading?: boolean;
  className?: string;
  valueClassName?: string;
}

export function StatCard({
  label,
  value,
  subValue,
  trend,
  trendLabel,
  icon: Icon,
  iconColor = 'text-primary',
  isLoading = false,
  className,
  valueClassName,
}: StatCardProps) {
  const TrendIcon =
    trend === undefined || trend === 0
      ? Minus
      : trend > 0
        ? TrendingUp
        : TrendingDown;

  const trendColor =
    trend === undefined || trend === 0
      ? 'text-muted-foreground'
      : trend > 0
        ? 'text-profit'
        : 'text-loss';

  if (isLoading) {
    return (
      <div
        className={cn(
          'bg-card border border-border rounded-xl p-5 animate-pulse',
          className
        )}
        aria-busy="true"
        aria-label={`Loading ${label}`}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="h-3 w-16 bg-muted rounded" />
          <div className="w-9 h-9 bg-muted rounded-lg" />
        </div>
        <div className="h-8 w-28 bg-muted rounded mb-2" />
        <div className="h-3 w-20 bg-muted rounded" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'bg-card border border-border rounded-xl p-5 hover:border-border/80 transition-all',
        className
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
          {label}
        </p>
        {Icon && (
          <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center', iconColor.replace('text-', 'bg-').replace('primary', 'primary/10').replace('profit', 'profit/10').replace('loss', 'loss/10'))}>
            <Icon className={cn('w-4 h-4', iconColor)} aria-hidden />
          </div>
        )}
      </div>

      <div
        className={cn(
          'font-mono text-2xl font-bold tracking-tight tabular-nums',
          valueClassName ?? 'text-foreground'
        )}
      >
        {value}
      </div>

      {(trend !== undefined || trendLabel || subValue) && (
        <div className="flex items-center gap-2 mt-2">
          <TrendIcon className={cn('w-3.5 h-3.5 flex-shrink-0', trendColor)} aria-hidden />
          <span className={cn('text-xs font-semibold', trendColor)}>
            {trendLabel ?? (trend !== undefined ? `${trend > 0 ? '+' : ''}${trend?.toFixed(2)}%` : '')}
          </span>
          {subValue && (
            <span className="text-xs text-muted-foreground font-medium">{subValue}</span>
          )}
        </div>
      )}
    </div>
  );
}
