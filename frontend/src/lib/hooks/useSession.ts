'use client';
import useSWR from 'swr';
import { useMarketStore } from '@/lib/store/marketStore';
import { api } from '@/lib/api';

export function useSession() {
  const setSession = useMarketStore((s) => s.setSession);
  const session = useMarketStore((s) => s.session);

  const { data, isLoading } = useSWR(
    'session',
    () => api.market.getSession(),
    {
      refreshInterval: 30_000,
      onSuccess: (data) => setSession(data),
    }
  );

  return {
    session: data ?? session,
    isLoading,
  };
}
