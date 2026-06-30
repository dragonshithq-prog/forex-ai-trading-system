'use client';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils/cn';
import { SESSION_COLORS } from '@/lib/utils/colors';
import { useSession } from '@/lib/hooks/useSession';
import type { SessionName } from '@/types/market';

const SESSION_FLAGS: Record<SessionName, string> = {
  Sydney: '🇦🇺',
  Tokyo: '🇯🇵',
  London: '🇬🇧',
  'New York': '🇺🇸',
};

const SESSION_HOURS: Record<SessionName, { open: number; close: number }> = {
  Sydney: { open: 22, close: 7 },
  Tokyo: { open: 0, close: 9 },
  London: { open: 8, close: 17 },
  'New York': { open: 13, close: 22 },
};

function getSessionStatus(name: SessionName): {
  isOpen: boolean;
  minutesRemaining: number;
  label: string;
} {
  const now = new Date();
  const utcHour = now.getUTCHours();
  const utcMinute = now.getUTCMinutes();
  const currentMinutes = utcHour * 60 + utcMinute;

  const { open, close } = SESSION_HOURS[name];
  const openMinutes = open * 60;
  const closeMinutes = close * 60;

  let isOpen = false;
  let minutesRemaining = 0;

  if (openMinutes < closeMinutes) {
    // Normal session (no midnight crossing)
    isOpen = currentMinutes >= openMinutes && currentMinutes < closeMinutes;
    minutesRemaining = isOpen
      ? closeMinutes - currentMinutes
      : currentMinutes < openMinutes
        ? openMinutes - currentMinutes
        : 24 * 60 - currentMinutes + openMinutes;
  } else {
    // Session crosses midnight (e.g., Sydney 22:00-07:00)
    isOpen = currentMinutes >= openMinutes || currentMinutes < closeMinutes;
    if (isOpen) {
      minutesRemaining =
        currentMinutes >= openMinutes
          ? 24 * 60 - currentMinutes + closeMinutes
          : closeMinutes - currentMinutes;
    } else {
      minutesRemaining = openMinutes - currentMinutes;
    }
  }

  const hours = Math.floor(minutesRemaining / 60);
  const mins = minutesRemaining % 60;
  const label = isOpen
    ? `Closes in ${hours}h ${mins}m`
    : `Opens in ${hours}h ${mins}m`;

  return { isOpen, minutesRemaining, label };
}

function formatUTCTime(): string {
  const now = new Date();
  return now.toUTCString().slice(17, 22) + ' UTC';
}

const SESSION_NAMES: SessionName[] = ['Sydney', 'Tokyo', 'London', 'New York'];

export function SessionClock() {
  const [statuses, setStatuses] = useState(() =>
    SESSION_NAMES.map((name) => ({ name, ...getSessionStatus(name) }))
  );
  const [utcTime, setUtcTime] = useState(formatUTCTime());

  // Update every 30 seconds
  useEffect(() => {
    const tick = () => {
      setStatuses(SESSION_NAMES.map((name) => ({ name, ...getSessionStatus(name) })));
      setUtcTime(formatUTCTime());
    };

    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);

  const openCount = statuses.filter((s) => s.isOpen).length;
  const isOverlap = openCount >= 2;

  return (
    <div className="space-y-2">
      {/* UTC clock header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Trading Sessions
        </h3>
        <div className="flex items-center gap-2">
          {isOverlap && (
            <span className="text-[10px] bg-yellow-500/10 text-yellow-400 px-1.5 py-0.5 rounded font-medium">
              Overlap
            </span>
          )}
          <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
            {utcTime}
          </span>
        </div>
      </div>

      {/* Session grid */}
      <div className="grid grid-cols-2 gap-2">
        {statuses.map(({ name, isOpen, label }) => {
          const colors = SESSION_COLORS[name];
          return (
            <div
              key={name}
              className={cn(
                'rounded-lg p-2.5 border transition-all',
                isOpen
                  ? `${colors.bg} ${colors.border}`
                  : 'bg-muted/20 border-border/50'
              )}
              role="status"
              aria-label={`${name} session: ${isOpen ? 'open' : 'closed'}. ${label}`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm" aria-hidden>
                    {SESSION_FLAGS[name]}
                  </span>
                  <span
                    className={cn(
                      'text-xs font-semibold',
                      isOpen ? colors.text : 'text-muted-foreground'
                    )}
                  >
                    {name === 'New York' ? 'NY' : name}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <div
                    className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      isOpen ? 'animate-pulse' : 'opacity-30'
                    )}
                    style={{ backgroundColor: isOpen ? colors.dot : '#555' }}
                    aria-hidden
                  />
                  <span
                    className={cn(
                      'text-[10px] font-medium uppercase tracking-wide',
                      isOpen ? colors.text : 'text-muted-foreground'
                    )}
                  >
                    {isOpen ? 'Open' : 'Closed'}
                  </span>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground truncate">{label}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
