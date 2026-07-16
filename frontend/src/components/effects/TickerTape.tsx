'use client'

import { useEffect, useState, useRef } from 'react'
import { cn } from '@/lib/utils/cn'

interface TickerItem {
  symbol: string
  price: number
  change: number
  changePercent: number
}

const fallbackItems: TickerItem[] = [
  { symbol: 'EUR/USD', price: 1.0923, change: 0.0012, changePercent: 0.11 },
  { symbol: 'GBP/USD', price: 1.2845, change: -0.0034, changePercent: -0.26 },
  { symbol: 'USD/JPY', price: 148.76, change: 0.45, changePercent: 0.30 },
  { symbol: 'AUD/USD', price: 0.6678, change: -0.0008, changePercent: -0.12 },
  { symbol: 'USD/CAD', price: 1.3590, change: 0.0021, changePercent: 0.15 },
  { symbol: 'NZD/USD', price: 0.6145, change: -0.0018, changePercent: -0.29 },
  { symbol: 'XAU/USD', price: 2045.30, change: 12.40, changePercent: 0.61 },
  { symbol: 'BTC/USD', price: 67540, change: 890, changePercent: 1.33 },
  { symbol: 'ETH/USD', price: 3450, change: -45, changePercent: -1.29 },
]

export function TickerTape({ items }: { items?: TickerItem[] }) {
  const data = items ?? fallbackItems
  const doubled = [...data, ...data]

  return (
    <div className="w-full overflow-hidden border-b border-border bg-card/80">
      <div className="ticker-tape flex whitespace-nowrap py-1.5">
        {doubled.map((item, i) => {
          const isUp = item.change >= 0
          return (
            <div key={`${item.symbol}-${i}`} className="flex items-center gap-2 mx-4 text-xs">
              <span className="font-semibold text-foreground">{item.symbol}</span>
              <span className="font-mono tabular-nums text-foreground">
                {item.price.toFixed(item.price < 100 ? 4 : 2)}
              </span>
              <span className={cn('font-mono tabular-nums', isUp ? 'text-profit' : 'text-loss')}>
                {isUp ? '+' : ''}{item.change.toFixed(item.change < 1 ? 4 : 2)}
              </span>
              <span className={cn('font-mono tabular-nums', isUp ? 'text-profit' : 'text-loss')}>
                ({isUp ? '+' : ''}{item.changePercent.toFixed(2)}%)
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
