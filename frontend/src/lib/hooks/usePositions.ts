'use client';
import useSWR from 'swr';
import { api } from '@/lib/api';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useEffect } from 'react';
import type { Position } from '@/types/trading';

export function usePositions() {
  const setPositions = useTradingStore((s) => s.setPositions);
  const setLoading = useTradingStore((s) => s.setLoadingPositions);
  const positions = useTradingStore((s) => s.positions);
  const isLoading = useTradingStore((s) => s.isLoadingPositions);

  const { data, error, mutate } = useSWR<Position[]>(
    'positions',
    () => api.trading.getPositions(),
    {
      refreshInterval: 5_000,
      onSuccess: (data) => {
        setPositions(data);
        setLoading(false);
      },
      onError: () => setLoading(false),
    }
  );

  useEffect(() => {
    if (!data) setLoading(true);
  }, [data, setLoading]);

  return {
    positions: data ?? positions,
    isLoading: !data && isLoading,
    error,
    refresh: mutate,
  };
}
