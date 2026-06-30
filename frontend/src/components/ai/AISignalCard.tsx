'use client';
import { TrendingUp, TrendingDown, Minus, Clock, Bot } from 'lucide-react';
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
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - confidence);
  const color =
    confidence >= 0.8 ? '#22c55e' : confidence >= 0.6 ? '#f59e0b' : '#ef4444';

  return (
    <div className="relative w-14 h-14 flex items-center justify-center" aria-hidden>
      <svg className="absolute -rotate-90" width={56} height={56}>
        <circle
          cx={28}
          cy={28}
          r={radius}
          fill="none"
          stroke="hsl(0 0% 13%)"
          strokeWidth={4}
        />
        <motion.circle
          cx={28}
          cy={28}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1, ease: 'easeOut' }}
        />
      </svg>
      <span className={cn('text-sm font-bold font-mono tabular-nums', getConfidenceColor(confidence))}>
        {Math.round(confidence * 100)}%
      </span>
    </div>
  );
}

export function AISignalCard({ signal, isLoading }: AISignalCardProps) {
  if (isLoading) {
    return (
      <div className="bg-card border border-border rounded-lg p-4 animate-pulse space-y-3">
        <div className="h-4 w-32 bg-muted rounded" />
        <div className="h-12 bg-muted rounded" />
        <div className="h-4 w-full bg-muted rounded" />
        <div className="h-4 w-3/4 bg-muted rounded" />
      </div>
    );
  }

  if (!signal) {
    return (
      <div className="bg-card border border-border rounded-lg p-4 flex flex-col items-center justify-center gap-3 min-h-[160px]">
        <div className="w-9 h-9 rounded-full bg-muted flex items-center justify-center">
          <Bot className="w-5 h-5 text-muted-foreground" aria-hidden />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">No active signal</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            AI is analyzing market conditions
          </p>
        </div>
      </div>
    );
  }

  const isBuy = signal.direction === 'BUY';
  const isHold = signal.direction === 'HOLD';

  const DirectionIcon = isHold ? Minus : isBuy ? TrendingUp : TrendingDown;
  const directionColor = isHold
    ? 'text-muted-foreground'
    : isBuy
      ? 'text-buy'
      : 'text-sell';

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
      className="bg-card border border-border rounded-lg p-4 space-y-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-primary" aria-hidden />
          <span className="text-sm font-semibold text-foreground">AI Signal</span>
        </div>
        <Badge variant="info" size="sm">{signal.strategy}</Badge>
      </div>

      {/* Main signal */}
      <div className="flex items-center gap-4">
        <ConfidenceRing confidence={signal.confidence} />

        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono font-bold text-lg text-foreground">{signal.symbol}</span>
            <div className={cn('flex items-center gap-1 font-semibold text-sm', directionColor)}>
              <DirectionIcon className="w-4 h-4" aria-hidden />
              <span>{signal.direction}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground font-mono">
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-0.5">Entry</div>
              <div className="text-foreground tabular-nums">
                {formatPrice(signal.entry_price, signal.symbol)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-0.5">SL</div>
              <div className="text-loss tabular-nums">
                {formatPrice(signal.stop_loss, signal.symbol)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-0.5">TP</div>
              <div className="text-profit tabular-nums">
                {formatPrice(signal.take_profit, signal.symbol)}
              </div>
            </div>
          </div>
        </div>

        <div className="text-right">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">R:R</div>
          <div className="font-mono font-bold text-foreground tabular-nums">
            {signal.risk_reward.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-xs text-muted-foreground leading-relaxed bg-muted/30 rounded px-2.5 py-2">
        {signal.reasoning}
      </p>

      {/* Agent breakdown */}
      <div className="space-y-1">
        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
          Supporting ({supportingAgents.length}) vs Conflicting ({conflictingAgents.length})
        </div>
        <div className="flex gap-1 flex-wrap">
          {supportingAgents.map((agent) => (
            <span
              key={agent.agent_name}
              className="text-[10px] bg-profit/10 text-profit px-1.5 py-0.5 rounded font-medium"
              title={agent.reasoning}
            >
              {agent.agent_name.replace(' Agent', '')}
            </span>
          ))}
          {conflictingAgents.map((agent) => (
            <span
              key={agent.agent_name}
              className="text-[10px] bg-loss/10 text-loss px-1.5 py-0.5 rounded font-medium"
              title={agent.reasoning}
            >
              {agent.agent_name.replace(' Agent', '')}
            </span>
          ))}
        </div>
      </div>

      {/* Expiry */}
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <Clock className="w-3 h-3" aria-hidden />
        <span>Generated {formatDateTime(signal.created_at)}</span>
      </div>
    </motion.div>
  );
}
