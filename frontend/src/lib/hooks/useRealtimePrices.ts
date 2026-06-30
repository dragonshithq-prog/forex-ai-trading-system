'use client';
import { useEffect, useRef, useState, useCallback } from 'react';

export interface LiveTick {
  type: 'tick';
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

export function useRealtimePrices(symbols: string[] = ['EURUSD', 'GBPUSD', 'USDJPY']) {
  const [ticks, setTicks] = useState<Record<string, LiveTick>>({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8003';
    try {
      const ws = new WebSocket(`${wsUrl}/api/v1/ws/live`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (mountedRef.current) setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const tick: LiveTick = JSON.parse(event.data);
          if (tick.type === 'tick') {
            setTicks((prev) => ({ ...prev, [tick.symbol]: tick }));
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        if (mountedRef.current) {
          setConnected(false);
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectRef.current = setTimeout(connect, 5000);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { ticks, connected };
}
