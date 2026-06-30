'use client';
import { useEffect, useState, useRef } from 'react';

interface TickerState {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
  direction: 'up' | 'down' | 'flat';
}

const BASE_PRICES: Record<string, number> = {
  EURUSD: 1.0850, GBPUSD: 1.2650, USDJPY: 151.50, AUDUSD: 0.6550,
  USDCAD: 1.3600, GBPJPY: 191.50, EURJPY: 164.50,
};

export function useRealtimeTicker(symbols: string[] = ['EURUSD', 'GBPUSD', 'USDJPY']) {
  const [prices, setPrices] = useState<Record<string, TickerState>>({});
  const driftRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const initial: Record<string, TickerState> = {};
    symbols.forEach((sym) => {
      const base = BASE_PRICES[sym] || 1.0;
      initial[sym] = {
        symbol: sym,
        bid: base - 0.0002,
        ask: base + 0.0002,
        spread: 0.0004,
        timestamp: new Date().toISOString(),
        direction: 'flat',
      };
      driftRef.current[sym] = 0;
    });
    setPrices(initial);

    const interval = setInterval(() => {
      setPrices((prev) => {
        const next = { ...prev };
        symbols.forEach((sym) => {
          const base = BASE_PRICES[sym] || 1.0;
          const current = prev[sym];
          if (!current) return;
          driftRef.current[sym] = (driftRef.current[sym] || 0) * 0.9 + (Math.random() - 0.5) * 0.0002;
          const change = driftRef.current[sym] + (Math.random() - 0.5) * 0.0001;
          const newBid = +(current.bid + change).toFixed(5);
          const spread = +(0.0002 + Math.random() * 0.0003).toFixed(5);
          next[sym] = {
            symbol: sym,
            bid: newBid,
            ask: +(newBid + spread).toFixed(5),
            spread,
            timestamp: new Date().toISOString(),
            direction: newBid > current.bid ? 'up' : newBid < current.bid ? 'down' : 'flat',
          };
        });
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [symbols]);

  return prices;
}
