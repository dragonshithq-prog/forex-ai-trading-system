'use client';
import { DollarSign, TrendingUp, Activity, BarChart2, Shield, BrainCircuit, Sparkles, Zap } from 'lucide-react';
import { AnimatedStatCard } from '@/components/effects/AnimatedStatCard';
import { AnimatedNumber } from '@/components/effects/AnimatedNumber';
import { MarketPulse } from '@/components/effects/MarketPulse';
import { AgentsNetwork } from '@/components/effects/AgentsNetwork';
import { TradingChart } from '@/components/charts/TradingChart';
import { PositionsList } from '@/components/trading/PositionsList';
import { SessionClock } from '@/components/session/SessionClock';
import { AISignalCard } from '@/components/ai/AISignalCard';
import { ConsensusGauge } from '@/components/ai/ConsensusGauge';
import { RiskDashboard } from '@/components/risk/RiskDashboard';
import { Watchlist } from '@/components/market/Watchlist';
import { MarketHeatmap } from '@/components/market/MarketHeatmap';
import { ActivityFeed } from '@/components/common/ActivityFeed';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useAISignals } from '@/lib/hooks/useAISignals';
import { useRiskState } from '@/lib/hooks/useRiskState';
import { usePositions } from '@/lib/hooks/usePositions';
import { useMarketStore } from '@/lib/store/marketStore';
import { formatCurrency, formatPnL, formatPercent } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { motion } from 'framer-motion';
import { useEffect, useCallback } from 'react';

const stagger = {
  animate: { transition: { staggerChildren: 0.06 } },
}

const fadeSlide = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.25, 0.1, 0.25, 1] } },
}

export function DashboardClient() {
  const account = useTradingStore((s) => s.account);
  const { signal, isLoading: signalLoading } = useAISignals();
  const { riskState } = useRiskState();
  const { positions } = usePositions();
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);

  const balance = account?.balance ?? 125_430.5;
  const equity = account?.equity ?? 126_842.3;
  const dayPnl = account?.day_pnl ?? 2340.5;
  const dayPnlPct = account?.day_pnl_pct ?? 1.87;
  const marginUsed = account?.margin_used ?? 8420;
  const freeMargin = account?.margin_available ?? 118_422;
  const marginLevel = account?.margin_used ? (equity / account.margin_used) * 100 : 999;

  const totalUnrealizedPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const winningPositions = positions.filter((p) => p.unrealized_pnl > 0).length;
  const winRate = positions.length > 0 ? (winningPositions / positions.length) * 100 : 0;

  const agentsAgreeing = signal?.agents.filter((a) => a.signal === signal.direction).length ?? 0;

  const handleSymbolSelect = useCallback((symbol: string) => {
    setSelectedSymbol(symbol);
  }, [setSelectedSymbol]);

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<string>;
      if (custom.detail) setSelectedSymbol(custom.detail);
    };
    window.addEventListener('symbol-select', handler as EventListener);
    return () => window.removeEventListener('symbol-select', handler as EventListener);
  }, [setSelectedSymbol]);

  return (
    <motion.div variants={stagger} initial="initial" animate="animate" className="space-y-5">
      {/* Header */}
      <motion.div variants={fadeSlide} className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            Dashboard
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-profit bg-profit/10 px-2 py-0.5 rounded-full">
              <Sparkles className="w-3 h-3" />
              Live
            </span>
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Market overview &amp; AI-powered trading insights
          </p>
        </div>
        <div className="flex items-center gap-3">
          <MarketPulse />
        </div>
      </motion.div>

      {/* Row 1: Premium Stat Cards */}
      <motion.div variants={fadeSlide} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <AnimatedStatCard
          label="Account Balance" value={balance} prefix="$"
          icon={DollarSign} trend={dayPnlPct}
          trendLabel={`${dayPnlPct > 0 ? '+' : ''}${dayPnlPct.toFixed(2)}% today`}
          delay={0}
        />
        <AnimatedStatCard
          label="Day P&L" value={dayPnl}
          formatter={(v) => formatPnL(v)}
          icon={TrendingUp}
          trend={dayPnlPct}
          iconColor={dayPnl >= 0 ? 'text-profit' : 'text-loss'}
          className={dayPnl >= 0 ? '' : ''}
          delay={0.05}
        >
          <div className="flex-1" />
          <span className={cn('text-xs font-semibold', getPnLColor(dayPnl))}>
            <AnimatedNumber value={Math.abs(dayPnl / balance * 100)} suffix="%" decimals={2} />
          </span>
        </AnimatedStatCard>
        <AnimatedStatCard
          label="Open Positions" value={positions.length} decimals={0}
          icon={Activity}
          subValue={positions.length > 0 ? `${formatPnL(totalUnrealizedPnl)} unrealized` : undefined}
          iconColor="text-blue-400"
          delay={0.1}
        />
        <AnimatedStatCard
          label="Floating P&L" value={totalUnrealizedPnl}
          formatter={(v) => formatPnL(v)}
          icon={BarChart2}
          trend={positions.length > 0 ? (totalUnrealizedPnl / balance) * 100 : 0}
          iconColor={totalUnrealizedPnl >= 0 ? 'text-profit' : 'text-loss'}
          delay={0.15}
        />
      </motion.div>

      {/* Row 2: Quick Stats */}
      <motion.div variants={fadeSlide} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card-hover bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Margin Used</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">
            <AnimatedNumber value={marginUsed} prefix="$" />
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            <AnimatedNumber value={(marginUsed / equity) * 100} suffix="%" decimals={1} /> of equity
          </div>
        </div>
        <div className="card-hover bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Free Margin</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">
            <AnimatedNumber value={freeMargin} prefix="$" />
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">Available for trading</div>
        </div>
        <div className="card-hover bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Margin Level</div>
          <div className={cn('font-mono text-sm font-semibold tabular-nums', marginLevel > 200 ? 'text-profit' : marginLevel > 100 ? 'text-yellow-400' : 'text-loss')}>
            {marginLevel > 999 ? '∞' : <AnimatedNumber value={marginLevel} suffix="%" decimals={0} />}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">Equity / Margin</div>
        </div>
        <div className="card-hover bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Win Rate</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">
            <AnimatedNumber value={winRate} suffix="%" decimals={1} />
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{winningPositions}/{positions.length} winners</div>
        </div>
      </motion.div>

      {/* Row 3: Chart + Right Panel */}
      <motion.div variants={fadeSlide} className="grid grid-cols-1 lg:grid-cols-5 gap-4" style={{ minHeight: '420px' }}>
        {/* Chart: 60% */}
        <div className="lg:col-span-3 h-[420px]">
          <ErrorBoundary>
            <TradingChart />
          </ErrorBoundary>
        </div>

        {/* Right panel: 40% */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          <div className="bg-card border border-border rounded-xl p-4">
            <ErrorBoundary>
              <SessionClock />
            </ErrorBoundary>
          </div>

          <div className="flex-1 overflow-hidden">
            <ErrorBoundary>
              <AISignalCard signal={signal} isLoading={signalLoading} />
            </ErrorBoundary>
          </div>

          {signal && (
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mb-2 text-center">
                Multi-Agent Consensus
              </div>
              <div className="flex items-center justify-center">
                <ConsensusGauge
                  confidence={signal.confidence}
                  direction={signal.direction}
                  agentCount={signal.agents.length}
                  agentsAgreeing={agentsAgreeing}
                />
              </div>
            </div>
          )}
        </div>
      </motion.div>

      {/* Row 4: AI Agents Network */}
      <motion.div variants={fadeSlide} className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <BrainCircuit className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">AI Agents Network</span>
          <span className="text-[10px] text-muted-foreground">Real-time consensus visualization</span>
        </div>
        <div className="flex items-center justify-center">
          <AgentsNetwork />
        </div>
      </motion.div>

      {/* Row 5: Positions + Risk */}
      <motion.div variants={fadeSlide} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-4">
          <ErrorBoundary>
            <PositionsList maxHeight="360px" />
          </ErrorBoundary>
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-muted-foreground" aria-hidden />
            <span className="text-sm font-semibold text-foreground">Risk Monitor</span>
            {riskState?.is_circuit_breaker_active && (
              <span className="text-[10px] bg-loss/10 text-loss px-1.5 py-0.5 rounded font-medium animate-pulse-soft">
                CIRCUIT BREAKER
              </span>
            )}
          </div>
          <ErrorBoundary>
            <RiskDashboard />
          </ErrorBoundary>
        </div>
      </motion.div>

      {/* Row 6: Watchlist + Heatmap + Activity */}
      <motion.div variants={fadeSlide} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-xl p-4">
          <Watchlist onSymbolSelect={handleSymbolSelect} />
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <MarketHeatmap />
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <ActivityFeed />
        </div>
      </motion.div>
    </motion.div>
  );
}
