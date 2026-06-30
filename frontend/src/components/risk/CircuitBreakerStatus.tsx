'use client';
import { ShieldOff, Shield } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { motion } from 'framer-motion';

interface CircuitBreakerStatusProps {
  isActive: boolean;
  reason?: string | null;
  activeUntil?: string | null;
}

export function CircuitBreakerStatus({
  isActive,
  reason,
  activeUntil,
}: CircuitBreakerStatusProps) {
  return (
    <motion.div
      animate={{
        borderColor: isActive ? 'hsl(0 84% 60% / 0.5)' : 'hsl(0 0% 13%)',
      }}
      className={cn(
        'rounded-lg p-3 border flex items-center gap-3 transition-colors',
        isActive ? 'bg-loss/10' : 'bg-profit/5'
      )}
      role="status"
      aria-live="polite"
      aria-label={`Circuit breaker: ${isActive ? 'active' : 'inactive'}`}
    >
      <div
        className={cn(
          'w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0',
          isActive ? 'bg-loss/20' : 'bg-profit/10'
        )}
      >
        {isActive ? (
          <ShieldOff className="w-4 h-4 text-loss" aria-hidden />
        ) : (
          <Shield className="w-4 h-4 text-profit" aria-hidden />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <p className={cn('text-sm font-semibold', isActive ? 'text-loss' : 'text-profit')}>
          Circuit Breaker: {isActive ? 'ACTIVE' : 'INACTIVE'}
        </p>
        {isActive && reason && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{reason}</p>
        )}
        {isActive && activeUntil && (
          <p className="text-xs text-muted-foreground mt-0.5">
            Until: {new Date(activeUntil).toLocaleTimeString()}
          </p>
        )}
        {!isActive && (
          <p className="text-xs text-muted-foreground mt-0.5">All systems normal</p>
        )}
      </div>

      <div
        className={cn(
          'w-2 h-2 rounded-full flex-shrink-0',
          isActive ? 'bg-loss animate-pulse' : 'bg-profit'
        )}
        aria-hidden
      />
    </motion.div>
  );
}
