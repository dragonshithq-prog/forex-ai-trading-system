'use client';
import { create } from 'zustand';
import type { RiskState, RiskAlert, RiskConfig } from '@/types/market';

interface RiskStoreState {
  state: RiskState | null;
  alerts: RiskAlert[];
  config: RiskConfig | null;
  unacknowledgedCount: number;

  setRiskState: (state: RiskState) => void;
  setAlerts: (alerts: RiskAlert[]) => void;
  addAlert: (alert: RiskAlert) => void;
  acknowledgeAlert: (id: string) => void;
  setConfig: (config: RiskConfig) => void;
}

export const useRiskStore = create<RiskStoreState>()((set) => ({
  state: null,
  alerts: [],
  config: null,
  unacknowledgedCount: 0,

  setRiskState: (state) => set({ state }),

  setAlerts: (alerts) =>
    set({
      alerts,
      unacknowledgedCount: alerts.filter((a) => !a.acknowledged).length,
    }),

  addAlert: (alert) =>
    set((prev) => {
      const exists = prev.alerts.find((a) => a.id === alert.id);
      if (exists) return prev;
      const alerts = [alert, ...prev.alerts].slice(0, 50);
      return {
        alerts,
        unacknowledgedCount: alerts.filter((a) => !a.acknowledged).length,
      };
    }),

  acknowledgeAlert: (id) =>
    set((prev) => {
      const alerts = prev.alerts.map((a) =>
        a.id === id ? { ...a, acknowledged: true } : a
      );
      return {
        alerts,
        unacknowledgedCount: alerts.filter((a) => !a.acknowledged).length,
      };
    }),

  setConfig: (config) => set({ config }),
}));
