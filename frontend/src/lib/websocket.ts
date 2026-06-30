'use client';
// WebSocket client + React hooks for real-time trading data

import { useEffect, useRef, useState, useCallback } from 'react';
import type { Tick, RiskAlert, SessionInfo } from '@/types/market';
import type { Position } from '@/types/trading';
import type { AISignal } from '@/types/api';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useRiskStore } from '@/lib/store/riskStore';
import { useMarketStore } from '@/lib/store/marketStore';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 30000];

type Handler = (data: unknown) => void;
type EventType = 'tick' | 'position_update' | 'order_update' | 'risk_alert' | 'ai_signal' | 'session_update' | 'connected' | 'disconnected';

// ---------------------------------------------------------------------------
// Core TradingWebSocket class
// ---------------------------------------------------------------------------

class TradingWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<Handler>> = new Map();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private isDestroyed = false;
  private token: string | null = null;

  connect(token: string): void {
    if (this.isDestroyed) return;
    this.token = token;

    try {
      const url = `${WS_URL}/ws?token=${encodeURIComponent(token)}`;
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
        this.startPing();
        this.emit('connected', {});

        // Auto-subscribe to all important channels
        this.subscribe('positions', {});
        this.subscribe('orders', {});
        this.subscribe('risk', {});
        this.subscribe('signals', {});
        this.subscribe('session', {});
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as {
            type: string;
            channel?: string;
            data?: unknown;
          };
          this.handleMessage(msg);
        } catch {
          // ignore parse errors
        }
      };

      this.ws.onerror = () => {
        console.warn('[WS] Connection error');
      };

      this.ws.onclose = (e) => {
        console.warn('[WS] Disconnected', e.code, e.reason);
        this.stopPing();
        this.emit('disconnected', {});
        if (!this.isDestroyed && e.code !== 1000) {
          this.scheduleReconnect();
        }
      };
    } catch (err) {
      console.warn('[WS] Failed to connect:', err);
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.isDestroyed = true;
    this.stopPing();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
  }

  subscribe(channel: string, params: object = {}): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'subscribe', channel, ...params }));
    }
  }

  unsubscribe(channel: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'unsubscribe', channel }));
    }
  }

  subscribeTick(symbols: string[]): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'subscribe', channel: 'ticks', symbols }));
    }
  }

  on(eventType: EventType | string, handler: Handler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
    return () => this.handlers.get(eventType)?.delete(handler);
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private handleMessage(msg: { type: string; channel?: string; data?: unknown }): void {
    const { type, channel, data } = msg;

    switch (type) {
      case 'pong':
        break;
      case 'tick':
        this.emit('tick', data);
        break;
      case 'position_update':
        this.emit('position_update', data);
        break;
      case 'order_update':
        this.emit('order_update', data);
        break;
      case 'risk_alert':
        this.emit('risk_alert', data);
        break;
      case 'signal':
        this.emit('ai_signal', data);
        break;
      case 'session_update':
        this.emit('session_update', data);
        break;
      default:
        if (channel) {
          this.emit(channel, data);
        }
    }
  }

  private emit(eventType: string, data: unknown): void {
    this.handlers.get(eventType)?.forEach((h) => {
      try {
        h(data);
      } catch (err) {
        console.error('[WS] Handler error:', err);
      }
    });
  }

  private startPing(): void {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 30_000);
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.isDestroyed) return;
    const delay = RECONNECT_DELAYS[Math.min(this.reconnectAttempts, RECONNECT_DELAYS.length - 1)];
    this.reconnectAttempts++;
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => {
      if (this.token && !this.isDestroyed) {
        this.connect(this.token);
      }
    }, delay);
  }
}

// Singleton instance
export const wsClient = new TradingWebSocket();

// ---------------------------------------------------------------------------
// Demo mode: simulate WebSocket events
// ---------------------------------------------------------------------------

let demoSimInterval: ReturnType<typeof setInterval> | null = null;

export function startDemoWebSocket(): void {
  if (!DEMO_MODE) return;
  if (demoSimInterval) return;

  const PAIRS = ['EURUSD', 'GBPJPY', 'USDJPY', 'AUDUSD'];
  const prices: Record<string, number> = {
    EURUSD: 1.08234,
    GBPJPY: 184.89,
    USDJPY: 149.18,
    AUDUSD: 0.65123,
  };

  demoSimInterval = setInterval(() => {
    // Emit random tick
    const symbol = PAIRS[Math.floor(Math.random() * PAIRS.length)];
    const isJpy = symbol.includes('JPY');
    const spread = isJpy ? 0.03 : 0.00015;
    const change = (Math.random() - 0.5) * (isJpy ? 0.05 : 0.0003);
    prices[symbol] = (prices[symbol] || 1.0) + change;
    const bid = prices[symbol];
    const ask = bid + spread;

    const tick: Tick = {
      symbol,
      bid: parseFloat(bid.toFixed(isJpy ? 3 : 5)),
      ask: parseFloat(ask.toFixed(isJpy ? 3 : 5)),
      spread: parseFloat(spread.toFixed(isJpy ? 3 : 5)),
      timestamp: new Date().toISOString(),
    };

    // Dispatch to market store directly in demo mode
    useMarketStore.getState().updateTick(tick);
  }, 800);
}

export function stopDemoWebSocket(): void {
  if (demoSimInterval) {
    clearInterval(demoSimInterval);
    demoSimInterval = null;
  }
}

// ---------------------------------------------------------------------------
// React Hooks
// ---------------------------------------------------------------------------

/** Hook: subscribe to real-time tick for a single symbol */
export function useTick(symbol: string): Tick | null {
  const tick = useMarketStore((s) => s.ticks[symbol]);
  const subscribedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!DEMO_MODE && symbol && symbol !== subscribedRef.current) {
      wsClient.subscribeTick([symbol]);
      subscribedRef.current = symbol;
    }
  }, [symbol]);

  useEffect(() => {
    if (DEMO_MODE) return;

    const cleanup = wsClient.on('tick', (data) => {
      const tickData = data as Tick;
      if (tickData?.symbol === symbol) {
        useMarketStore.getState().updateTick(tickData);
      }
    });
    return cleanup;
  }, [symbol]);

  return tick ?? null;
}

/** Hook: receive position updates and sync to trading store */
export function usePositionUpdates(): void {
  useEffect(() => {
    if (DEMO_MODE) return;

    const cleanup = wsClient.on('position_update', (data) => {
      const position = data as Position;
      if (position?.position_id) {
        useTradingStore.getState().updatePosition(position);
      }
    });
    return cleanup;
  }, []);
}

/** Hook: receive risk alerts */
export function useRiskAlerts(): RiskAlert[] {
  const alerts = useRiskStore((s) => s.alerts);

  useEffect(() => {
    if (DEMO_MODE) return;

    const cleanup = wsClient.on('risk_alert', (data) => {
      const alert = data as RiskAlert;
      if (alert?.id) {
        useRiskStore.getState().addAlert(alert);
      }
    });
    return cleanup;
  }, []);

  return alerts;
}

/** Hook: receive latest AI signal */
export function useAISignals(): AISignal | null {
  const [signal, setSignal] = useState<AISignal | null>(null);

  useEffect(() => {
    if (DEMO_MODE) return;

    const cleanup = wsClient.on('ai_signal', (data) => {
      setSignal(data as AISignal);
    });
    return cleanup;
  }, []);

  return signal;
}

/** Hook: WebSocket connection status */
export function useWSStatus(): 'connected' | 'disconnected' {
  const [status, setStatus] = useState<'connected' | 'disconnected'>('disconnected');

  useEffect(() => {
    if (DEMO_MODE) {
      setStatus('connected');
      return;
    }

    const cleanupConn = wsClient.on('connected', () => setStatus('connected'));
    const cleanupDisc = wsClient.on('disconnected', () => setStatus('disconnected'));

    return () => {
      cleanupConn();
      cleanupDisc();
    };
  }, []);

  return status;
}

/** Hook: connect WebSocket on mount with JWT token */
export function useWSConnection(): void {
  useEffect(() => {
    if (DEMO_MODE) {
      startDemoWebSocket();
      return () => stopDemoWebSocket();
    }

    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token) {
      wsClient.connect(token);
    }

    return () => {
      wsClient.disconnect();
    };
  }, []);
}
