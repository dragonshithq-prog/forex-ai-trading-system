'use client'

import { useEffect, useCallback, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowUpCircle, ArrowDownCircle, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

interface TradeAlert {
  id: string
  symbol: string
  side: 'buy' | 'sell'
  volume: number
  price: number
  timestamp: Date
  pnl?: number
}

export function TradeNotification() {
  const [alerts, setAlerts] = useState<TradeAlert[]>([])

  const addAlert = useCallback((alert: TradeAlert) => {
    setAlerts(prev => [alert, ...prev].slice(0, 5))
    setTimeout(() => {
      setAlerts(prev => prev.filter(a => a.id !== alert.id))
    }, 5000)
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<TradeAlert>
      addAlert(custom.detail)
    }
    window.addEventListener('trade-executed', handler as EventListener)
    return () => window.removeEventListener('trade-executed', handler as EventListener)
  }, [addAlert])

  const remove = (id: string) => setAlerts(prev => prev.filter(a => a.id !== id))

  return (
    <div className="fixed bottom-6 left-6 z-50 flex flex-col gap-2 max-w-xs">
      <AnimatePresence>
        {alerts.map(alert => (
          <motion.div
            key={alert.id}
            initial={{ opacity: 0, x: -50, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -50, scale: 0.9 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            className={cn(
              'bg-card border rounded-xl p-3 shadow-2xl flex items-start gap-3',
              alert.side === 'buy' ? 'border-profit/30' : 'border-loss/30'
            )}
          >
            {alert.side === 'buy' ? (
              <ArrowUpCircle className="w-5 h-5 text-profit flex-shrink-0 mt-0.5" />
            ) : (
              <ArrowDownCircle className="w-5 h-5 text-loss flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-foreground">{alert.symbol}</span>
                <span className={cn(
                  'text-[10px] uppercase font-bold px-1.5 py-0.5 rounded',
                  alert.side === 'buy' ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'
                )}>
                  {alert.side}
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {alert.volume} lots @ {alert.price.toFixed(5)}
              </div>
              {alert.pnl !== undefined && (
                <div className={cn('text-xs font-mono font-semibold mt-0.5', alert.pnl >= 0 ? 'text-profit' : 'text-loss')}>
                  {alert.pnl >= 0 ? '+' : ''}{alert.pnl.toFixed(2)} USD
                </div>
              )}
            </div>
            <button onClick={() => remove(alert.id)} className="text-muted-foreground hover:text-foreground transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
