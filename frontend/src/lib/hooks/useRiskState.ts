'use client';
import useSWR from 'swr';
import { useRiskStore } from '@/lib/store/riskStore';
import { api } from '@/lib/api';

export function useRiskState() {
  const setRiskState = useRiskStore((s) => s.setRiskState);
  const setAlerts = useRiskStore((s) => s.setAlerts);
  const riskState = useRiskStore((s) => s.state);
  const alerts = useRiskStore((s) => s.alerts);

  const { data: stateData, isLoading: loadingState } = useSWR(
    'risk-state',
    () => api.risk.getState(),
    {
      refreshInterval: 5_000,
      onSuccess: (data) => setRiskState(data),
    }
  );

  const { data: alertsData, isLoading: loadingAlerts } = useSWR(
    'risk-alerts',
    () => api.risk.getAlerts(),
    {
      refreshInterval: 10_000,
      onSuccess: (data) => setAlerts(data),
    }
  );

  return {
    riskState: stateData ?? riskState,
    alerts: alertsData ?? alerts,
    isLoading: loadingState,
  };
}

export function useRiskConfig() {
  const setConfig = useRiskStore((s) => s.setConfig);

  const { data, isLoading, mutate } = useSWR(
    'risk-config',
    () => api.risk.getConfig(),
    { onSuccess: (data) => setConfig(data) }
  );

  return { config: data, isLoading, refresh: mutate };
}
