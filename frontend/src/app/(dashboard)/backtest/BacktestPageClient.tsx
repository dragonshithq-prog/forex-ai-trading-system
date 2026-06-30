'use client';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { FlaskConical, Play, Loader2, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { EquityCurve } from '@/components/charts/EquityCurve';
import { MonthlyReturns } from '@/components/charts/MonthlyReturns';
import { formatPercent, formatNumber, formatCurrency } from '@/lib/utils/formatters';
import type { BacktestResult } from '@/types/api';

const backtestSchema = z.object({
  strategy: z.string().min(1),
  symbol: z.string().min(6).max(10),
  timeframe: z.string().min(1),
  start_date: z.string().min(10),
  end_date: z.string().min(10),
  initial_balance: z.number().min(100).max(10_000_000),
  risk_pct: z.number().min(0.1).max(10),
});

type BacktestFormValues = z.infer<typeof backtestSchema>;

const STRATEGIES = ['ICT_Momentum', 'Mean_Reversion', 'Breakout', 'Trend_Following', 'Scalping'];
const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD'];
const TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'];

function ResultMetric({
  label,
  value,
  variant = 'neutral',
}: {
  label: string;
  value: string;
  variant?: 'positive' | 'negative' | 'neutral';
}) {
  return (
    <div className="bg-muted/30 rounded-lg p-3 text-center">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div
        className={cn(
          'font-mono font-bold text-lg tabular-nums',
          variant === 'positive' ? 'text-profit' : variant === 'negative' ? 'text-loss' : 'text-foreground'
        )}
      >
        {value}
      </div>
    </div>
  );
}

export function BacktestPageClient() {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<BacktestFormValues>({
    resolver: zodResolver(backtestSchema),
    defaultValues: {
      strategy: 'ICT_Momentum',
      symbol: 'EURUSD',
      timeframe: 'H1',
      start_date: '2023-01-01',
      end_date: '2023-12-31',
      initial_balance: 10_000,
      risk_pct: 1.0,
    },
  });

  const onSubmit = async (data: BacktestFormValues) => {
    setIsRunning(true);
    setResult(null);
    try {
      const id = await api.analytics.runBacktest(data);
      setRunId(id);
      toast.info('Backtest started. Fetching results...');

      // Poll for results
      let attempts = 0;
      const poll = async () => {
        attempts++;
        const res = await api.analytics.getBacktestResult(id);
        if (res.status === 'completed') {
          setResult(res);
          setIsRunning(false);
          toast.success('Backtest completed!');
        } else if (res.status === 'failed') {
          setIsRunning(false);
          toast.error('Backtest failed. Please check your parameters.');
        } else if (attempts < 30) {
          setTimeout(poll, 2000);
        } else {
          setIsRunning(false);
          toast.error('Backtest timed out.');
        }
      };
      await poll();
    } catch {
      setIsRunning(false);
      toast.error('Failed to start backtest. Please try again.');
    }
  };

  const inputClass = cn(
    'w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground',
    'focus:outline-none focus:ring-2 focus:ring-ring transition-colors',
    'placeholder:text-muted-foreground/50 font-mono'
  );
  const labelClass = 'block text-xs text-muted-foreground font-medium mb-1.5';
  const errorClass = 'text-xs text-loss mt-1';

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Backtesting Workspace</h1>
        <p className="text-sm text-muted-foreground">Test strategies against historical market data</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Config form */}
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-4">
            <FlaskConical className="w-4 h-4 text-primary" aria-hidden />
            <h2 className="text-sm font-semibold text-foreground">Configuration</h2>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-3" noValidate>
            <div>
              <label htmlFor="bt-strategy" className={labelClass}>Strategy</label>
              <select id="bt-strategy" {...register('strategy')} className={inputClass}>
                {STRATEGIES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="bt-symbol" className={labelClass}>Symbol</label>
                <select id="bt-symbol" {...register('symbol')} className={inputClass}>
                  {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="bt-timeframe" className={labelClass}>Timeframe</label>
                <select id="bt-timeframe" {...register('timeframe')} className={inputClass}>
                  {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="bt-start" className={labelClass}>Start Date</label>
                <input id="bt-start" type="date" {...register('start_date')} className={inputClass} />
                {errors.start_date && <p className={errorClass} role="alert">{errors.start_date.message}</p>}
              </div>
              <div>
                <label htmlFor="bt-end" className={labelClass}>End Date</label>
                <input id="bt-end" type="date" {...register('end_date')} className={inputClass} />
                {errors.end_date && <p className={errorClass} role="alert">{errors.end_date.message}</p>}
              </div>
            </div>

            <div>
              <label htmlFor="bt-balance" className={labelClass}>Initial Balance ($)</label>
              <input
                id="bt-balance"
                type="number"
                {...register('initial_balance', { valueAsNumber: true })}
                className={inputClass}
                placeholder="10000"
              />
              {errors.initial_balance && <p className={errorClass} role="alert">{errors.initial_balance.message}</p>}
            </div>

            <div>
              <label htmlFor="bt-risk" className={labelClass}>Risk Per Trade (%)</label>
              <input
                id="bt-risk"
                type="number"
                step="0.1"
                {...register('risk_pct', { valueAsNumber: true })}
                className={inputClass}
                placeholder="1.0"
              />
              {errors.risk_pct && <p className={errorClass} role="alert">{errors.risk_pct.message}</p>}
            </div>

            <button
              type="submit"
              disabled={isRunning}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-md bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {isRunning ? (
                <><Loader2 className="w-4 h-4 animate-spin" aria-hidden />Running...</>
              ) : (
                <><Play className="w-4 h-4" aria-hidden />Run Backtest</>
              )}
            </button>
          </form>
        </div>

        {/* Results panel */}
        <div className="lg:col-span-2 space-y-4">
          {isRunning && (
            <div className="bg-card border border-border rounded-lg p-8 flex flex-col items-center gap-3">
              <div className="w-10 h-10 rounded-full border-2 border-muted border-t-primary animate-spin" />
              <p className="text-sm text-muted-foreground">Running backtest simulation...</p>
            </div>
          )}

          {result && !isRunning && (
            <>
              {/* Key metrics */}
              <div className="bg-card border border-border rounded-lg p-4">
                <h2 className="text-sm font-semibold text-foreground mb-4">
                  Results: {result.strategy} on {result.symbol} {result.timeframe}
                </h2>
                <div className="grid grid-cols-4 gap-3 mb-4">
                  <ResultMetric
                    label="Total Return"
                    value={formatPercent(result.total_return_pct, 2, true)}
                    variant={result.total_return_pct >= 0 ? 'positive' : 'negative'}
                  />
                  <ResultMetric
                    label="Sharpe"
                    value={formatNumber(result.sharpe_ratio)}
                    variant={result.sharpe_ratio >= 1.5 ? 'positive' : 'neutral'}
                  />
                  <ResultMetric
                    label="Win Rate"
                    value={formatPercent(result.win_rate)}
                    variant={result.win_rate >= 55 ? 'positive' : 'neutral'}
                  />
                  <ResultMetric
                    label="Max DD"
                    value={`-${formatPercent(result.max_drawdown_pct)}`}
                    variant={result.max_drawdown_pct <= 10 ? 'positive' : 'negative'}
                  />
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <ResultMetric label="Profit Factor" value={formatNumber(result.profit_factor)} variant={result.profit_factor >= 1.5 ? 'positive' : 'neutral'} />
                  <ResultMetric label="Total Trades" value={result.total_trades.toString()} />
                  <ResultMetric label="Final Balance" value={formatCurrency(result.final_balance)} variant={result.final_balance > result.initial_balance ? 'positive' : 'negative'} />
                  <ResultMetric label="Sortino" value={formatNumber(result.sortino_ratio)} variant={result.sortino_ratio >= 2 ? 'positive' : 'neutral'} />
                </div>
              </div>

              {/* Equity curve */}
              <div className="bg-card border border-border rounded-lg p-4">
                <h3 className="text-sm font-semibold text-foreground mb-3">Equity Curve</h3>
                <div className="h-44">
                  <EquityCurve data={result.equity_curve} />
                </div>
              </div>

              {/* Monthly returns */}
              <div className="bg-card border border-border rounded-lg p-4">
                <h3 className="text-sm font-semibold text-foreground mb-3">Monthly Returns</h3>
                <MonthlyReturns data={result.monthly_returns} />
              </div>
            </>
          )}

          {!result && !isRunning && (
            <div className="bg-card border border-border rounded-lg p-8 flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-muted-foreground" aria-hidden />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Configure and run a backtest</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Results and performance metrics will appear here
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
