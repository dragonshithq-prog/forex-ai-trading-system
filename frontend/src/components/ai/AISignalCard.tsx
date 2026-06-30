'use client';
import { TrendingUp, TrendingDown, Minus, Clock, Bot, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils/cn';
import { Badge } from '@/components/common/Badge';
import { formatPrice, formatDateTime } from '@/lib/utils/formatters';
import { getConfidenceColor } from '@/lib/utils/colors';
import type { AISignal } from '@/types/api';

interface AISignalCardProps {
  signal: AISignal | null;
  isLoading?: boolean;
}

function ConfidenceRing({ confidence }: { confidence: number }) {
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - confidence);
  const color =
    confidence >= 0.8 ? '#22c55e' : confidence >= 0.6 ? '#f59e0b' : '#ef4444';

  return (
    <div className="relative w-16 h-16 flex items-center justify-center flex-shrink-0" aria-hidden>
      <svg className="absolute -rotate-90" width={64} height={64}>
        <circle
          cx={32}
          cy={32}
          r={radius}
          fill="none"
          stroke="hsl(0 0% 13%)"
          strokeWidth={5}
        />
        <motion.circle
          cx={32}
          cy={32}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        />
      </svg>
      <span className={cn('text-base font-bold font-mono tabular-nums', getConfidenceColor(confidence))}>
        {Math.round(confidence * 100)}%
      </span>
    </div>
  );
}

export function AISignalCard({ signal, isLoading }: AISignalCardProps) {
  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-xl p-5 animate-pulse space-y-4">
        <div className="h-5 w-28 bg-muted rounded" />
        <div className="h-16 bg-muted rounded-lg" />
        <div className="h-4 w-full bg-muted rounded" />
        <div className="h-4 w-3/4 bg-muted rounded" />
        <div className="h-8 w-full bg-muted rounded" />
      </div>
    );
  }

  if (!signal) {
    return (
      <div className="bg-card border border-border rounded-xl p-5 flex flex-col items-center justify-center gap-3 min-h-[200px]">
        <div className="w-11 h-11 rounded-full bg-muted flex items-center justify-center">
          <Bot className="w-6 h-6 text-muted-foreground" aria-hidden />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">No active signal</p>
          <p className="text-xs text-muted-foreground mt-1">
            AI is analyzing market conditions
          </p>
        </div>
      </div>
    );
  }

  const isBuy = signal.direction === 'BUY';
  const isHold = signal.direction === 'HOLD';
  const isSell = signal.direction === 'SELL';

  const DirectionIcon = isHold ? Minus : isBuy ? TrendingUp : TrendingDown;
  const directionColor = isHold
    ? 'text-muted-foreground'
    : isBuy
      ? 'text-buy'
      : 'text-sell';
  const directionBg = isHold
    ? 'bg-muted text-muted-foreground'
    : isBuy
      ? 'bg-buy/10 text-buy border-buy/20'
      : 'bg-sell/10 text-sell border-sell/20';

  const supportingAgents = signal.agents.filter(
    (a) => a.signal === signal.direction
  );
  const conflictingAgents = signal.agents.filter(
    (a) => a.signal !== signal.direction && a.signal !== 'NEUTRAL'
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-card border border-border rounded-xl p-5 space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Bot className="w-4 h-4 text-primary" aria-hidden />
          </div>
          <span className="text-sm font-semibold text-foreground">AI Signal</span>
        </div>
        <Badge variant="info" size="sm">{signal.strategy}</Badge>
      </div>

      {/* Symbol + Direction + Confidence */}
      <div className="flex items-center gap-4">
        <ConfidenceRing confidence={signal.confidence} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 mb-2">
            <span className="font-mono font-bold text-xl text-foreground tracking-tight">{signal.symbol}</span>
            <span className={cn('flex items-center gap-1 font-bold text-sm px-2.5 py-1 rounded-md border', directionBg)}>
              <DirectionIcon className="w-3.5 h-3.5" aria-hidden />
              <span>{signal.direction}</span>
            </span>
          </div>

          {/* Entry / SL / TP / R:R grid */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-muted/40 rounded-lg px-2.5 py-2">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1 font-medium">Entry</div>
              <div className="text-sm font-semibold text-foreground font-mono tabular-nums">
                {formatPrice(signal.entry_price, signal.symbol)}
              </div>
            </div>
            <div className="bg-loss/5 rounded-lg px-2.5 py-2 border border-loss/10">
              <div className="text-[10px] text-loss/70 uppercase tracking-wider mb-1 font-medium">Stop Loss</div>
              <div className="text-sm font-semibold text-loss font-mono tabular-nums">
                {formatPrice(signal.stop_loss, signal.symbol)}
              </div>
            </div>
            <div className="bg-profit/5 rounded-lg px-2.5 py-2 border border-profit/10">
              <div className="text-[10px] text-profit/70 uppercase tracking-wider mb-1 font-medium">Take Profit</div>
              <div className="text-sm font-semibold text-profit font-mono tabular-nums">
                {formatPrice(signal.take_profit, signal.symbol)}
              </div>
            </div>
            <div className="bg-muted/40 rounded-lg px-2.5 py-2">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1 font-medium">Risk:Reward</div>
              <div className="text-sm font-bold text-foreground font-mono tabular-nums">
                1:{signal.risk_reward.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Reasoning */}
      <div className="bg-muted/30 border border-border/50 rounded-lg px-3.5 py-2.5">
        <p className="text-xs text-muted-foreground leading-relaxed">{signal.reasoning}</p>
      </div>

      {/* Agent breakdown */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">
            Agent Consensus
          </span>
          <span className="text-[10px] text-muted-foreground font-medium">
            {supportingAgents.length} agree · {conflictingAgents.length} disagree
          </span>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {supportingAgents.map((agent) => (
            <span
              key={agent.agent_name}
              className="text-[10px] bg-profit/10 text-profit border border-profit/15 px-2 py-1 rounded-md font-medium"
              title={agent.reasoning}
            >
              {agent.agent_name.replace(' Agent', '')}
            </span>
          ))}
          {conflictingAgents.map((agent) => (
            <span
              key={agent.agent_name}
              className="text-[10px] bg-loss/10 text-loss border border-loss/15 px-2 py-1 rounded-md font-medium"
              title={agent.reasoning}
            >
              {agent.agent_name.replace(' Agent', '')}
            </span>
          ))}
        </div>
      </div>

      {/* Expiry */}
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground pt-1 border-t border-border/50">
        <Clock className="w-3 h-3" aria-hidden />
        <span>Signal generated {formatDateTime(signal.created_at)}</span>
        <span className="text-muted-foreground/50">·</span>
        <span>Expires {formatDateTime(signal.expires_at)}</span>
      </div>
    </motion.div>
  );
}
