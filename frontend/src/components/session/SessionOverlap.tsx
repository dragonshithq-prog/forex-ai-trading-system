'use client';
import { cn } from '@/lib/utils/cn';
import type { SessionInfo } from '@/types/market';

interface SessionOverlapProps {
  session: SessionInfo | null;
}

const OVERLAP_LABELS: Record<string, string> = {
  'Sydney-Tokyo': 'Sydney/Tokyo Overlap (Asian)',
  'Tokyo-London': 'Tokyo/London Overlap (Transition)',
  'London-New York': 'London/NY Overlap (Highest Liquidity)',
};

export function SessionOverlap({ session }: SessionOverlapProps) {
  if (!session) return null;

  const { is_overlap, sessions_active } = session;

  if (!is_overlap || sessions_active.length < 2) {
    return null;
  }

  const key = sessions_active.slice(0, 2).join('-');
  const label = OVERLAP_LABELS[key] ?? `${sessions_active.join('/')} Overlap`;

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-lg border',
        'bg-yellow-500/5 border-yellow-500/20 text-yellow-400'
      )}
      role="status"
      aria-label={`Session overlap: ${label}`}
    >
      <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" aria-hidden />
      <span className="text-xs font-medium">{label}</span>
    </div>
  );
}
