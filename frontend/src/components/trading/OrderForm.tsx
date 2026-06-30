'use client';
import { useState, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TrendingUp, TrendingDown, Loader2, Calculator, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useTradingStore } from '@/lib/store/tradingStore';

const orderSchema = z.object({
  symbol: z.string().min(6).max(10),
  side: z.enum(['buy', 'sell']),
  quantity: z.number().positive().max(100),
  order_type: z.enum(['market', 'limit', 'stop', 'stop_limit']),
  price: z.number().optional(),
  stop_loss: z.number().optional(),
  take_profit: z.number().optional(),
  trailing_stop: z.number().optional(),
  comment: z.string().optional(),
});

type OrderFormValues = z.infer<typeof orderSchema>;

const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'EURJPY'];

const PIP_VALUES: Record<string, number> = {
  EURUSD: 10, GBPUSD: 10, AUDUSD: 10, NZDUSD: 10, EURGBP: 10,
  GBPJPY: 0.01, USDJPY: 0.01, EURJPY: 0.01,
  USDCAD: 10, USDCHF: 10,
};

export function OrderForm({ onSuccess }: { onSuccess?: () => void }) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [riskAmount, setRiskAmount] = useState(100);
  const account = useTradingStore((s) => s.account);
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<OrderFormValues>({
    resolver: zodResolver(orderSchema),
    defaultValues: {
      symbol: 'EURUSD',
      side: 'buy',
      quantity: 0.1,
      order_type: 'market',
    },
  });

  const orderType = watch('order_type');
  const symbol = watch('symbol');
  const quantity = watch('quantity') || 0;
  const stopLoss = watch('stop_loss');
  const takeProfit = watch('take_profit');
  const entryPrice = watch('price') || 1.08234;

  const isJpy = symbol.includes('JPY');
  const pipValue = PIP_VALUES[symbol] || 10;
  const balance = account?.balance ?? 125_430.5;

  const riskCalc = useMemo(() => {
    if (!stopLoss || !quantity) return null;
    const slDistance = Math.abs(entryPrice - stopLoss);
    const slPips = isJpy ? slDistance * 100 : slDistance * 10000;
    const riskPerLot = slPips * pipValue;
    const totalRisk = riskPerLot * quantity;
    const riskPct = (totalRisk / balance) * 100;
    return {
      slPips: slPips.toFixed(1),
      riskPerLot: riskPerLot.toFixed(2),
      totalRisk: totalRisk.toFixed(2),
      riskPct: riskPct.toFixed(2),
      isOverRisk: riskPct > 2,
    };
  }, [stopLoss, quantity, entryPrice, isJpy, pipValue, balance]);

  const rewardCalc = useMemo(() => {
    if (!takeProfit || !stopLoss || !quantity) return null;
    const slDistance = Math.abs(entryPrice - stopLoss);
    const tpDistance = Math.abs(takeProfit - entryPrice);
    const rr = slDistance > 0 ? tpDistance / slDistance : 0;
    return {
      rr: rr.toFixed(2),
      tpPips: isJpy ? tpDistance * 100 : tpDistance * 10000,
    };
  }, [takeProfit, stopLoss, quantity, entryPrice, isJpy]);

  const onSubmit = async (data: OrderFormValues) => {
    try {
      await api.trading.placeOrder({ ...data, side });
      toast.success(`${side.toUpperCase()} order placed for ${data.symbol}`);
      reset();
      onSuccess?.();
    } catch {
      toast.error('Failed to place order. Check your inputs and try again.');
    }
  };

  const labelClass = 'block text-xs text-muted-foreground mb-1.5 font-medium';
  const inputClass = cn(
    'w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring',
    'font-mono tabular-nums transition-colors'
  );
  const errorClass = 'text-xs text-loss mt-1';

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3" noValidate>
      {/* Buy/Sell toggle */}
      <div
        className="flex rounded-md overflow-hidden border border-border"
        role="group"
        aria-label="Trade direction"
      >
        <button
          type="button"
          onClick={() => setSide('buy')}
          className={cn(
            'flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            side === 'buy'
              ? 'bg-buy/20 text-buy border-buy/30'
              : 'bg-transparent text-muted-foreground hover:text-foreground'
          )}
          aria-pressed={side === 'buy'}
        >
          <TrendingUp className="w-4 h-4" aria-hidden />
          Buy
        </button>
        <div className="w-px bg-border" />
        <button
          type="button"
          onClick={() => setSide('sell')}
          className={cn(
            'flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            side === 'sell'
              ? 'bg-sell/20 text-sell border-sell/30'
              : 'bg-transparent text-muted-foreground hover:text-foreground'
          )}
          aria-pressed={side === 'sell'}
        >
          <TrendingDown className="w-4 h-4" aria-hidden />
          Sell
        </button>
      </div>

      {/* Symbol */}
      <div>
        <label htmlFor="order-symbol" className={labelClass}>Symbol</label>
        <select id="order-symbol" {...register('symbol')} className={inputClass}>
          {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {errors.symbol && <p className={errorClass} role="alert">{errors.symbol.message}</p>}
      </div>

      {/* Order type + Quantity */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="order-type" className={labelClass}>Order Type</label>
          <select id="order-type" {...register('order_type')} className={inputClass}>
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
            <option value="stop_limit">Stop Limit</option>
          </select>
        </div>
        <div>
          <label htmlFor="order-quantity" className={labelClass}>Quantity (lots)</label>
          <input id="order-quantity" type="number" step="0.01" min="0.01" {...register('quantity', { valueAsNumber: true })} className={inputClass} placeholder="0.10" />
          {errors.quantity && <p className={errorClass} role="alert">{errors.quantity.message}</p>}
        </div>
      </div>

      {/* Price (for limit/stop) */}
      {orderType !== 'market' && (
        <div>
          <label htmlFor="order-price" className={labelClass}>Price</label>
          <input id="order-price" type="number" step="0.00001" {...register('price', { valueAsNumber: true })} className={inputClass} placeholder="1.08500" />
          {errors.price && <p className={errorClass} role="alert">{errors.price.message}</p>}
        </div>
      )}

      {/* SL/TP */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="order-sl" className={labelClass}>Stop Loss</label>
          <input id="order-sl" type="number" step="0.00001" {...register('stop_loss', { valueAsNumber: true })} className={inputClass} placeholder="Optional" />
        </div>
        <div>
          <label htmlFor="order-tp" className={labelClass}>Take Profit</label>
          <input id="order-tp" type="number" step="0.00001" {...register('take_profit', { valueAsNumber: true })} className={inputClass} placeholder="Optional" />
        </div>
      </div>

      {/* Risk Calculator */}
      {riskCalc && (
        <div className={cn('rounded-lg border p-3', riskCalc.isOverRisk ? 'bg-loss/5 border-loss/20' : 'bg-muted/20 border-border/50')}>
          <div className="flex items-center gap-2 mb-2">
            <Calculator className="w-3.5 h-3.5 text-muted-foreground" aria-hidden />
            <span className="text-xs font-semibold text-foreground">Risk Calculator</span>
            {riskCalc.isOverRisk && (
              <span className="flex items-center gap-1 text-[10px] text-loss font-medium">
                <AlertTriangle className="w-3 h-3" aria-hidden />
                Over 2% risk
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <span className="text-muted-foreground">SL Distance:</span>
              <span className="font-mono text-foreground ml-1">{riskCalc.slPips} pips</span>
            </div>
            <div>
              <span className="text-muted-foreground">Risk/Lot:</span>
              <span className="font-mono text-foreground ml-1">${riskCalc.riskPerLot}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Total Risk:</span>
              <span className={cn('font-mono ml-1', riskCalc.isOverRisk ? 'text-loss' : 'text-foreground')}>${riskCalc.totalRisk}</span>
            </div>
            <div>
              <span className="text-muted-foreground">% of Balance:</span>
              <span className={cn('font-mono ml-1', riskCalc.isOverRisk ? 'text-loss' : 'text-foreground')}>{riskCalc.riskPct}%</span>
            </div>
          </div>
          {rewardCalc && (
            <div className="mt-2 pt-2 border-t border-border/50 grid grid-cols-2 gap-2 text-[10px]">
              <div>
                <span className="text-muted-foreground">TP Distance:</span>
                <span className="font-mono text-profit ml-1">{rewardCalc.tpPips.toFixed(1)} pips</span>
              </div>
              <div>
                <span className="text-muted-foreground">Risk:Reward:</span>
                <span className="font-mono text-foreground ml-1">1:{rewardCalc.rr}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className={cn('transition-transform', showAdvanced ? 'rotate-90' : '')}>▶</span>
        Advanced Options
      </button>

      {showAdvanced && (
        <div className="space-y-3 pl-4 border-l-2 border-border/50">
          <div>
            <label htmlFor="order-tsl" className={labelClass}>Trailing Stop (pips)</label>
            <input id="order-tsl" type="number" step="1" min="0" {...register('trailing_stop', { valueAsNumber: true })} className={inputClass} placeholder="Optional" />
          </div>
          <div>
            <label htmlFor="order-comment" className={labelClass}>Comment</label>
            <input id="order-comment" type="text" {...register('comment')} className={inputClass} placeholder="Optional note" />
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={isSubmitting}
        className={cn(
          'w-full flex items-center justify-center gap-2 py-3 rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 disabled:cursor-not-allowed',
          side === 'buy'
            ? 'bg-buy hover:bg-buy/90 text-white'
            : 'bg-sell hover:bg-sell/90 text-white'
        )}
      >
        {isSubmitting ? (
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
        ) : side === 'buy' ? (
          <TrendingUp className="w-4 h-4" aria-hidden />
        ) : (
          <TrendingDown className="w-4 h-4" aria-hidden />
        )}
        {isSubmitting ? 'Placing...' : `Place ${side.toUpperCase()} Order`}
      </button>
    </form>
  );
}
