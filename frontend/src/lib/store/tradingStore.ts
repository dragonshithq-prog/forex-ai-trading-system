'use client';
import { create } from 'zustand';
import type { Position, Order } from '@/types/trading';
import type { AccountSummary } from '@/types/trading';

interface TradingState {
  positions: Position[];
  orders: Order[];
  account: AccountSummary | null;
  isLoadingPositions: boolean;
  isLoadingOrders: boolean;

  setPositions: (positions: Position[]) => void;
  updatePosition: (position: Position) => void;
  removePosition: (id: string) => void;
  setOrders: (orders: Order[]) => void;
  setAccount: (account: AccountSummary) => void;
  setLoadingPositions: (loading: boolean) => void;
  setLoadingOrders: (loading: boolean) => void;
}

export const useTradingStore = create<TradingState>()((set) => ({
  positions: [],
  orders: [],
  account: null,
  isLoadingPositions: false,
  isLoadingOrders: false,

  setPositions: (positions) => set({ positions }),

  updatePosition: (updated) =>
    set((state) => {
      const idx = state.positions.findIndex((p) => p.position_id === updated.position_id);
      if (idx === -1) {
        return { positions: [...state.positions, updated] };
      }
      const next = [...state.positions];
      next[idx] = { ...next[idx], ...updated };
      return { positions: next };
    }),

  removePosition: (id) =>
    set((state) => ({
      positions: state.positions.filter((p) => p.position_id !== id),
    })),

  setOrders: (orders) => set({ orders }),

  setAccount: (account) => set({ account }),

  setLoadingPositions: (isLoadingPositions) => set({ isLoadingPositions }),

  setLoadingOrders: (isLoadingOrders) => set({ isLoadingOrders }),
}));
