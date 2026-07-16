'use client'

import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Minus, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { AnimatedNumber } from './AnimatedNumber'
import type { ReactNode } from 'react'

interface AnimatedStatCardProps {
  label: string
  value: number
  prefix?: string
  suffix?: string
  decimals?: number
  subValue?: string
  trend?: number
  trendLabel?: string
  icon?: LucideIcon
  iconColor?: string
  formatter?: (v: number) => string
  className?: string
  delay?: number
  children?: ReactNode
}

export function AnimatedStatCard({
  label,
  value,
  prefix = '',
  suffix = '',
  decimals = 2,
  subValue,
  trend,
  trendLabel,
  icon: Icon,
  iconColor = 'text-primary',
  formatter,
  className,
  delay = 0,
  children,
}: AnimatedStatCardProps) {
  const TrendIcon = trend === undefined || trend === 0 ? Minus : trend > 0 ? TrendingUp : TrendingDown
  const trendColor = trend === undefined || trend === 0 ? 'text-muted-foreground' : trend > 0 ? 'text-profit' : 'text-loss'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.1, 0.25, 1] }}
      className={cn(
        'card-hover bg-card border border-border rounded-xl p-5',
        className
      )}
    >
      <div className="flex items-start justify-between mb-4">
        <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">{label}</p>
        {Icon && (
          <div className={cn(
            'w-9 h-9 rounded-lg flex items-center justify-center',
            iconColor.replace('text-', 'bg-').replace('primary', 'primary/10').replace('profit', 'profit/10').replace('loss', 'loss/10')
          )}>
            <Icon className={cn('w-4 h-4', iconColor)} aria-hidden />
          </div>
        )}
      </div>

      <div className="font-mono text-2xl font-bold tracking-tight tabular-nums text-foreground">
        {formatter ? (
          <AnimatedNumber value={value} formatter={formatter} />
        ) : (
          <AnimatedNumber value={value} prefix={prefix} suffix={suffix} decimals={decimals} />
        )}
      </div>

      {(trend !== undefined || trendLabel || subValue || children) && (
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          {trend !== undefined && (
            <TrendIcon className={cn('w-3.5 h-3.5 flex-shrink-0', trendColor)} aria-hidden />
          )}
          {trendLabel && (
            <span className={cn('text-xs font-semibold', trendColor)}>{trendLabel}</span>
          )}
          {!trendLabel && trend !== undefined && (
            <span className={cn('text-xs font-semibold', trendColor)}>
              {trend > 0 ? '+' : ''}{trend.toFixed(2)}%
            </span>
          )}
          {subValue && <span className="text-xs text-muted-foreground font-medium">{subValue}</span>}
          {children}
        </div>
      )}
    </motion.div>
  )
}
