import { cn } from '@/lib/utils/cn';
import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'success' | 'danger' | 'warning' | 'info' | 'buy' | 'sell' | 'neutral';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'bg-muted text-muted-foreground',
  success: 'bg-profit/10 text-profit',
  danger: 'bg-loss/10 text-loss',
  warning: 'bg-yellow-500/10 text-yellow-400',
  info: 'bg-blue-500/10 text-blue-400',
  buy: 'bg-buy/15 text-buy',
  sell: 'bg-sell/15 text-sell',
  neutral: 'bg-muted text-muted-foreground',
};

const dotColors: Record<BadgeVariant, string> = {
  default: 'bg-muted-foreground',
  success: 'bg-profit',
  danger: 'bg-loss',
  warning: 'bg-yellow-400',
  info: 'bg-blue-400',
  buy: 'bg-buy',
  sell: 'bg-sell',
  neutral: 'bg-muted-foreground',
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'text-[10px] px-1.5 py-0.5',
  md: 'text-xs px-2 py-1',
};

export function Badge({
  children,
  variant = 'default',
  size = 'md',
  dot = false,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded font-medium leading-none',
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
    >
      {dot && (
        <span
          className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', dotColors[variant])}
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}
