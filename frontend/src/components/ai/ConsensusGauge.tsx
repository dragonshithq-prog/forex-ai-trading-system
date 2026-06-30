'use client';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils/cn';
import { getConfidenceColor } from '@/lib/utils/colors';

interface ConsensusGaugeProps {
  confidence: number; // 0-1
  direction?: 'BUY' | 'SELL' | 'HOLD';
  agentCount?: number;
  agentsAgreeing?: number;
}

export function ConsensusGauge({
  confidence,
  direction = 'HOLD',
  agentCount = 0,
  agentsAgreeing = 0,
}: ConsensusGaugeProps) {
  // SVG arc gauge
  const SIZE = 120;
  const CENTER = SIZE / 2;
  const RADIUS = 44;
  const STROKE = 8;
  const START_ANGLE = 210; // degrees (left)
  const END_ANGLE = 330;   // degrees (right arc = 240deg total sweep)
  const SWEEP = 240;

  const toRad = (deg: number) => (deg * Math.PI) / 180;

  function polarToCart(angle: number): { x: number; y: number } {
    return {
      x: CENTER + RADIUS * Math.cos(toRad(angle)),
      y: CENTER + RADIUS * Math.sin(toRad(angle)),
    };
  }

  // Background arc path
  const bgStart = polarToCart(START_ANGLE);
  const bgEnd = polarToCart(START_ANGLE + SWEEP);
  const bgPath = `M ${bgStart.x} ${bgStart.y} A ${RADIUS} ${RADIUS} 0 1 1 ${bgEnd.x} ${bgEnd.y}`;

  // Foreground arc
  const filledSweep = SWEEP * confidence;
  const fgEnd = polarToCart(START_ANGLE + filledSweep);
  const largeArc = filledSweep > 180 ? 1 : 0;
  const fgPath = `M ${bgStart.x} ${bgStart.y} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${fgEnd.x} ${fgEnd.y}`;

  const gaugeColor =
    confidence >= 0.8
      ? '#22c55e'
      : confidence >= 0.6
        ? '#f59e0b'
        : '#ef4444';

  const directionBg =
    direction === 'BUY'
      ? 'bg-buy/10 text-buy'
      : direction === 'SELL'
        ? 'bg-sell/10 text-sell'
        : 'bg-muted text-muted-foreground';

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: SIZE, height: SIZE * 0.75 }}>
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="overflow-visible"
          aria-label={`Consensus gauge: ${Math.round(confidence * 100)}% confidence`}
          role="img"
        >
          {/* Background arc */}
          <path
            d={bgPath}
            fill="none"
            stroke="hsl(0 0% 13%)"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
          {/* Foreground arc */}
          <motion.path
            d={fgPath}
            fill="none"
            stroke={gaugeColor}
            strokeWidth={STROKE}
            strokeLinecap="round"
            pathLength={1}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: confidence }}
            transition={{ duration: 1, ease: 'easeOut' }}
          />
        </svg>

        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center mt-2">
          <span
            className={cn(
              'text-2xl font-bold font-mono tabular-nums',
              getConfidenceColor(confidence)
            )}
          >
            {Math.round(confidence * 100)}%
          </span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Consensus
          </span>
        </div>
      </div>

      {/* Direction badge */}
      <span
        className={cn(
          'text-xs font-semibold px-3 py-1 rounded-full',
          directionBg
        )}
      >
        {direction}
      </span>

      {agentCount > 0 && (
        <p className="text-[10px] text-muted-foreground text-center">
          {agentsAgreeing}/{agentCount} agents agree
        </p>
      )}
    </div>
  );
}
