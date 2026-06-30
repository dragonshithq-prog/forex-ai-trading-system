'use client';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils/cn';
import type { AgentSignal } from '@/types/api';

interface AgentBreakdownProps {
  agents: AgentSignal[];
}

function SignalBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
      <motion.div
        className={cn('h-full rounded-full', color)}
        initial={{ width: 0 }}
        animate={{ width: `${value * 100}%` }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      />
    </div>
  );
}

export function AgentBreakdown({ agents }: AgentBreakdownProps) {
  return (
    <div className="space-y-2" role="table" aria-label="Agent signals breakdown">
      <div className="grid grid-cols-[1fr,auto,auto,auto] gap-2 text-[10px] text-muted-foreground uppercase tracking-wider pb-1 border-b border-border">
        <span>Agent</span>
        <span className="w-12 text-center">Signal</span>
        <span className="w-16 text-right">Conf.</span>
        <span className="w-12 text-right">Wt.</span>
      </div>
      {agents.map((agent) => {
        const signalColor =
          agent.signal === 'BUY'
            ? 'text-buy'
            : agent.signal === 'SELL'
              ? 'text-sell'
              : 'text-muted-foreground';
        const barColor =
          agent.signal === 'BUY'
            ? 'bg-buy'
            : agent.signal === 'SELL'
              ? 'bg-sell'
              : 'bg-muted-foreground';

        return (
          <div
            key={agent.agent_name}
            role="row"
            className="grid grid-cols-[1fr,auto,auto,auto] gap-2 items-center"
            title={agent.reasoning}
          >
            <div className="text-xs text-foreground truncate">{agent.agent_name}</div>
            <div className={cn('w-12 text-center text-[10px] font-semibold', signalColor)}>
              {agent.signal}
            </div>
            <div className="w-16 flex items-center gap-1.5">
              <SignalBar value={agent.confidence} color={barColor} />
              <span className="text-[10px] text-muted-foreground font-mono tabular-nums w-6">
                {Math.round(agent.confidence * 100)}%
              </span>
            </div>
            <div className="w-12 text-right text-[10px] text-muted-foreground font-mono tabular-nums">
              {(agent.weight * 100).toFixed(0)}%
            </div>
          </div>
        );
      })}
    </div>
  );
}
