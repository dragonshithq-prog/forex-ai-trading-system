'use client';
import { create } from 'zustand';
import type { Tick, Candle, SessionInfo } from '@/types/market';
import type { AISignal } from '@/types/api';

interface MarketState {
  ticks: Record<string, Tick>;
  candles: Record<string, Candle[]>; // key: `${symbol}_${timeframe}`
  session: SessionInfo | null;
  latestSignal: AISignal | null;
  selectedSymbol: string;
  selectedTimeframe: string;
  currencyStrength: Record<string, number>;

  updateTick: (tick: Tick) => void;
  setCandles: (symbol: string, timeframe: string, candles: Candle[]) => void;
  setSession: (session: SessionInfo) => void;
  setLatestSignal: (signal: AISignal) => void;
  setSelectedSymbol: (symbol: string) => void;
  setSelectedTimeframe: (timeframe: string) => void;
  setCurrencyStrength: (data: Record<string, number>) => void;
}

export const useMarketStore = create<MarketState>()((set) => ({
  ticks: {},
  candles: {},
  session: null,
  latestSignal: null,
  selectedSymbol: 'EURUSD',
  selectedTimeframe: 'H1',
  currencyStrength: {},

  updateTick: (tick) =>
    set((state) => ({
      ticks: { ...state.ticks, [tick.symbol]: tick },
    })),

  setCandles: (symbol, timeframe, candles) =>
    set((state) => ({
      candles: { ...state.candles, [`${symbol}_${timeframe}`]: candles },
    })),

  setSession: (session) => set({ session }),

  setLatestSignal: (latestSignal) => set({ latestSignal }),

  setSelectedSymbol: (selectedSymbol) => set({ selectedSymbol }),

  setSelectedTimeframe: (selectedTimeframe) => set({ selectedTimeframe }),

  setCurrencyStrength: (currencyStrength) => set({ currencyStrength }),
}));
