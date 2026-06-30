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
          'bg-card border border-border rounded-lg p-4 animate-pulse',
          className
        )}
        aria-busy="true"
        aria-label={`Loading ${label}`}
      >
        <div className="flex items-start justify-between mb-3">
          <div className="h-3 w-16 bg-muted rounded" />
          <div className="w-8 h-8 bg-muted rounded-md" />
        </div>
        <div className="h-7 w-24 bg-muted rounded mb-1" />
        <div className="h-3 w-20 bg-muted rounded" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'bg-card border border-border rounded-lg p-4 hover:border-border/80 transition-colors',
        className
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
          {label}
        </p>
        {Icon && (
          <div className={cn('w-8 h-8 rounded-md flex items-center justify-center bg-muted/50', iconColor.replace('text-', 'bg-').replace('primary', 'primary/10').replace('profit', 'profit/10').replace('loss', 'loss/10'))}>
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
        <div className="flex items-center gap-1.5 mt-1.5">
          <TrendIcon className={cn('w-3 h-3 flex-shrink-0', trendColor)} aria-hidden />
          <span className={cn('text-xs font-medium', trendColor)}>
            {trendLabel ?? (trend !== undefined ? `${trend > 0 ? '+' : ''}${trend?.toFixed(2)}%` : '')}
          </span>
          {subValue && (
            <span className="text-xs text-muted-foreground">{subValue}</span>
          )}
        </div>
      )}
    </div>
  );
}
