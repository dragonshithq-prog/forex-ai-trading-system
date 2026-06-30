'use client';
import useSWR from 'swr';
import { useEffect } from 'react';
import { api } from '@/lib/api';
import { useMarketStore } from '@/lib/store/marketStore';
import type { Candle } from '@/types/market';

export function useMarketData(symbol: string, timeframe: string) {
  const setCandles = useMarketStore((s) => s.setCandles);
  const candles = useMarketStore((s) => s.candles[`${symbol}_${timeframe}`]);
  const setSession = useMarketStore((s) => s.setSession);
  const session = useMarketStore((s) => s.session);

  const { data: candleData, isLoading: loadingCandles } = useSWR<Candle[]>(
    ['candles', symbol, timeframe],
    () => api.market.getCandles(symbol, timeframe, 300),
    {
      refreshInterval: 60_000,
      onSuccess: (data) => setCandles(symbol, timeframe, data),
    }
  );

  const { data: sessionData } = useSWR(
    'session',
    () => api.market.getSession(),
    {
      refreshInterval: 60_000,
      onSuccess: (data) => setSession(data),
    }
  );

  useEffect(() => {
    if (sessionData) setSession(sessionData);
  }, [sessionData, setSession]);

  return {
    candles: candleData ?? candles ?? [],
    session: sessionData ?? session,
    isLoading: loadingCandles && !candles?.length,
  };
}

export function useCurrencyStrength() {
  const setCurrencyStrength = useMarketStore((s) => s.setCurrencyStrength);
  const { data, isLoading } = useSWR(
    'currency-strength',
    () => api.market.getCurrencyStrength(),
    {
      refreshInterval: 60_000,
      onSuccess: (data) => setCurrencyStrength(data),
    }
  );
  return { strength: data ?? {}, isLoading };
}
