'use client';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const orderSchema = z.object({
  symbol: z.string().min(6).max(10),
  side: z.enum(['buy', 'sell']),
  quantity: z.number().positive().max(100),
  order_type: z.enum(['market', 'limit', 'stop', 'stop_limit']),
  price: z.number().optional(),
  stop_loss: z.number().optional(),
  take_profit: z.number().optional(),
  comment: z.string().optional(),
});

type OrderFormValues = z.infer<typeof orderSchema>;

const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'EURJPY'];

export function OrderForm({ onSuccess }: { onSuccess?: () => void }) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
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
        <label htmlFor="order-symbol" className={labelClass}>
          Symbol
        </label>
        <select
          id="order-symbol"
          {...register('symbol')}
          className={inputClass}
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {errors.symbol && <p className={errorClass} role="alert">{errors.symbol.message}</p>}
      </div>

      {/* Order type + Quantity */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="order-type" className={labelClass}>
            Order Type
          </label>
          <select
            id="order-type"
            {...register('order_type')}
            className={inputClass}
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
            <option value="stop_limit">Stop Limit</option>
          </select>
        </div>

        <div>
          <label htmlFor="order-quantity" className={labelClass}>
            Quantity (lots)
          </label>
          <input
            id="order-quantity"
            type="number"
            step="0.01"
            min="0.01"
            {...register('quantity', { valueAsNumber: true })}
            className={inputClass}
            placeholder="0.10"
          />
          {errors.quantity && <p className={errorClass} role="alert">{errors.quantity.message}</p>}
        </div>
      </div>

      {/* Price (for limit/stop) */}
      {orderType !== 'market' && (
        <div>
          <label htmlFor="order-price" className={labelClass}>
            Price
          </label>
          <input
            id="order-price"
            type="number"
            step="0.00001"
            {...register('price', { valueAsNumber: true })}
            className={inputClass}
            placeholder="1.08500"
          />
          {errors.price && <p className={errorClass} role="alert">{errors.price.message}</p>}
        </div>
      )}

      {/* SL/TP */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="order-sl" className={labelClass}>
            Stop Loss
          </label>
          <input
            id="order-sl"
            type="number"
            step="0.00001"
            {...register('stop_loss', { valueAsNumber: true })}
            className={inputClass}
            placeholder="Optional"
          />
        </div>
        <div>
          <label htmlFor="order-tp" className={labelClass}>
            Take Profit
          </label>
          <input
            id="order-tp"
            type="number"
            step="0.00001"
            {...register('take_profit', { valueAsNumber: true })}
            className={inputClass}
            placeholder="Optional"
          />
        </div>
      </div>

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
