'use client';
import useSWR from 'swr';
import { useMarketStore } from '@/lib/store/marketStore';
import { api } from '@/lib/api';
import type { AISignal } from '@/types/api';

export function useAISignals() {
  const setLatestSignal = useMarketStore((s) => s.setLatestSignal);
  const latestSignal = useMarketStore((s) => s.latestSignal);

  const { data, isLoading } = useSWR<AISignal | null>(
    'latest-signal',
    () => api.signals.getLatest(),
    {
      refreshInterval: 30_000,
      onSuccess: (data) => { if (data) setLatestSignal(data); },
    }
  );

  return {
    signal: data ?? latestSignal,
    isLoading,
  };
}
