'use client';
import useSWR from 'swr';
import { api } from '@/lib/api';
import type { Order } from '@/types/trading';
import type { OrdersParams } from '@/types/api';

export function useOrders(params?: OrdersParams) {
  const { data, error, isLoading, mutate } = useSWR(
    ['orders', params],
    () => api.trading.getOrders(params),
    { refreshInterval: 10_000 }
  );

  return {
    orders: (data?.items ?? []) as Order[],
    total: data?.total ?? 0,
    pages: data?.pages ?? 1,
    isLoading,
    error,
    refresh: mutate,
  };
}
