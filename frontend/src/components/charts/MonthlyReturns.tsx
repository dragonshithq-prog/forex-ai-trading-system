'use client';
import { useMemo } from 'react';
import { cn } from '@/lib/utils/cn';

interface MonthlyReturnsProps {
  data: Record<string, number>; // key: 'YYYY-MM', value: return_pct
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function getColor(value: number): string {
  if (value === 0) return 'bg-muted text-muted-foreground';
  const abs = Math.abs(value);
  const intensity = Math.min(abs / 5, 1); // cap at 5% for full intensity

  if (value > 0) {
    if (intensity > 0.8) return 'bg-green-600/70 text-white';
    if (intensity > 0.5) return 'bg-green-600/50 text-green-100';
    if (intensity > 0.2) return 'bg-green-600/30 text-green-300';
    return 'bg-green-600/15 text-green-400';
  } else {
    if (intensity > 0.8) return 'bg-red-600/70 text-white';
    if (intensity > 0.5) return 'bg-red-600/50 text-red-100';
    if (intensity > 0.2) return 'bg-red-600/30 text-red-300';
    return 'bg-red-600/15 text-red-400';
  }
}

export function MonthlyReturns({ data }: MonthlyReturnsProps) {
  const years = useMemo(() => {
    const yearSet = new Set<number>();
    Object.keys(data).forEach((key) => {
      yearSet.add(parseInt(key.split('-')[0]));
    });
    return Array.from(yearSet).sort((a, b) => b - a);
  }, [data]);

  const yearlyTotals = useMemo(() => {
    const totals: Record<number, number> = {};
    Object.entries(data).forEach(([key, value]) => {
      const year = parseInt(key.split('-')[0]);
      totals[year] = (totals[year] ?? 0) + value;
    });
    return totals;
  }, [data]);

  if (!years.length) {
    return (
      <div className="flex items-center justify-center p-8 text-sm text-muted-foreground">
        No monthly return data available
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" role="table" aria-label="Monthly returns heatmap">
        <thead>
          <tr>
            <th className="text-left text-muted-foreground font-medium py-1.5 pr-3 w-12">Year</th>
            {MONTHS.map((m) => (
              <th
                key={m}
                className="text-center text-muted-foreground font-medium py-1.5 px-0.5 w-12"
              >
                {m}
              </th>
            ))}
            <th className="text-center text-muted-foreground font-medium py-1.5 px-2 w-14">
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {years.map((year) => (
            <tr key={year}>
              <td className="text-muted-foreground font-medium py-0.5 pr-3">{year}</td>
              {MONTHS.map((_, monthIdx) => {
                const key = `${year}-${String(monthIdx + 1).padStart(2, '0')}`;
                const value = data[key];
                const hasData = value !== undefined;
                return (
                  <td key={monthIdx} className="py-0.5 px-0.5">
                    {hasData ? (
                      <div
                        className={cn(
                          'rounded px-0.5 py-1 text-center font-mono tabular-nums text-[10px] min-w-[40px]',
                          getColor(value)
                        )}
                        title={`${MONTHS[monthIdx]} ${year}: ${value >= 0 ? '+' : ''}${value.toFixed(2)}%`}
                        role="cell"
                        aria-label={`${MONTHS[monthIdx]} ${year}: ${value.toFixed(2)}%`}
                      >
                        {value >= 0 ? '+' : ''}{value.toFixed(1)}%
                      </div>
                    ) : (
                      <div className="rounded px-0.5 py-1 min-w-[40px]" />
                    )}
                  </td>
                );
              })}
              <td className="py-0.5 px-2">
                <div
                  className={cn(
                    'rounded px-1 py-1 text-center font-mono tabular-nums text-[10px] font-semibold',
                    getColor(yearlyTotals[year] ?? 0)
                  )}
                >
                  {(yearlyTotals[year] ?? 0) >= 0 ? '+' : ''}
                  {(yearlyTotals[year] ?? 0).toFixed(1)}%
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
