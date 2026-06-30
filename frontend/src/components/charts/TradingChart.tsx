'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import type { IChartApi, ISeriesApi, CandlestickData, UTCTimestamp } from 'lightweight-charts';
import { useMarketStore } from '@/lib/store/marketStore';
import { useMarketData } from '@/lib/hooks/useMarketData';
import { useMarketStore as useStore } from '@/lib/store/marketStore';
import { cn } from '@/lib/utils/cn';
import { ChevronDown } from 'lucide-react';

const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'EURJPY'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'] as const;

const CHART_THEME = {
  background: '#0a0a0a',
  text: '#a1a1aa',
  grid: '#1c1c1c',
  border: '#222222',
  upColor: '#22c55e',
  downColor: '#ef4444',
  wickUp: '#22c55e',
  wickDown: '#ef4444',
  ema20: '#f59e0b',
  ema50: '#8b5cf6',
  ema200: '#ec4899',
  volume: 'rgba(59, 130, 246, 0.25)',
};

interface EMASeries {
  ema20?: ISeriesApi<'Line'>;
  ema50?: ISeriesApi<'Line'>;
  ema200?: ISeriesApi<'Line'>;
}

function calcEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [];
  let ema = data[0];
  for (let i = 0; i < data.length; i++) {
    ema = i === 0 ? data[0] : data[i] * k + ema * (1 - k);
    result.push(ema);
  }
  return result;
}

export function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaSeriesRef = useRef<EMASeries>({});
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const selectedTimeframe = useMarketStore((s) => s.selectedTimeframe);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setSelectedTimeframe = useMarketStore((s) => s.setSelectedTimeframe);
  const ticks = useMarketStore((s) => s.ticks);

  const [showEMA20, setShowEMA20] = useState(true);
  const [showEMA50, setShowEMA50] = useState(true);
  const [showEMA200, setShowEMA200] = useState(true);
  const [showSymbolMenu, setShowSymbolMenu] = useState(false);

  const { candles, isLoading } = useMarketData(selectedSymbol, selectedTimeframe);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Dynamically import to avoid SSR issues
    import('lightweight-charts').then(({ createChart, CrosshairMode }) => {
      if (!chartContainerRef.current) return;

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { color: CHART_THEME.background },
          textColor: CHART_THEME.text,
          fontFamily: 'var(--font-inter), system-ui, sans-serif',
          fontSize: 11,
        },
        grid: {
          vertLines: { color: CHART_THEME.grid },
          horzLines: { color: CHART_THEME.grid },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: '#444',
            width: 1,
            style: 3,
            labelBackgroundColor: '#333',
          },
          horzLine: {
            color: '#444',
            width: 1,
            style: 3,
            labelBackgroundColor: '#333',
          },
        },
        rightPriceScale: {
          borderColor: CHART_THEME.border,
          textColor: CHART_THEME.text,
          scaleMargins: { top: 0.1, bottom: 0.25 },
        },
        timeScale: {
          borderColor: CHART_THEME.border,
          timeVisible: true,
          secondsVisible: false,
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor: CHART_THEME.upColor,
        downColor: CHART_THEME.downColor,
        borderUpColor: CHART_THEME.upColor,
        borderDownColor: CHART_THEME.downColor,
        wickUpColor: CHART_THEME.wickUp,
        wickDownColor: CHART_THEME.wickDown,
      });

      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
        color: CHART_THEME.volume,
      });

      chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });

      const ema20 = chart.addLineSeries({
        color: CHART_THEME.ema20,
        lineWidth: 1,
        title: 'EMA 20',
        visible: showEMA20,
      });
      const ema50 = chart.addLineSeries({
        color: CHART_THEME.ema50,
        lineWidth: 1,
        title: 'EMA 50',
        visible: showEMA50,
      });
      const ema200 = chart.addLineSeries({
        color: CHART_THEME.ema200,
        lineWidth: 1,
        title: 'EMA 200',
        visible: showEMA200,
      });

      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      volumeSeriesRef.current = volumeSeries;
      emaSeriesRef.current = { ema20, ema50, ema200 };

      // Resize observer
      const ro = new ResizeObserver(() => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.resize(
            chartContainerRef.current.clientWidth,
            chartContainerRef.current.clientHeight
          );
        }
      });
      ro.observe(chartContainerRef.current);
      resizeObserverRef.current = ro;
    });

    return () => {
      resizeObserverRef.current?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update data when candles change
  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return;

    const candleData: CandlestickData[] = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumeData = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)',
    }));

    const closes = candles.map((c) => c.close);
    const times = candles.map((c) => (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp);

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current?.setData(volumeData);

    // EMA calculations
    const ema20Data = calcEMA(closes, 20).map((v, i) => ({ time: times[i], value: v }));
    const ema50Data = calcEMA(closes, 50).map((v, i) => ({ time: times[i], value: v }));
    const ema200Data = calcEMA(closes, 200).map((v, i) => ({ time: times[i], value: v }));

    emaSeriesRef.current.ema20?.setData(ema20Data);
    emaSeriesRef.current.ema50?.setData(ema50Data);
    emaSeriesRef.current.ema200?.setData(ema200Data);

    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Update last candle with live tick
  useEffect(() => {
    const tick = ticks[selectedSymbol];
    if (!tick || !candleSeriesRef.current || !candles.length) return;

    const last = candles[candles.length - 1];
    if (!last) return;

    const time = (new Date(last.timestamp).getTime() / 1000) as UTCTimestamp;
    candleSeriesRef.current.update({
      time,
      open: last.open,
      high: Math.max(last.high, tick.bid),
      low: Math.min(last.low, tick.bid),
      close: tick.bid,
    });
  }, [ticks, selectedSymbol, candles]);

  // Toggle EMA visibility
  useEffect(() => {
    emaSeriesRef.current.ema20?.applyOptions({ visible: showEMA20 });
  }, [showEMA20]);
  useEffect(() => {
    emaSeriesRef.current.ema50?.applyOptions({ visible: showEMA50 });
  }, [showEMA50]);
  useEffect(() => {
    emaSeriesRef.current.ema200?.applyOptions({ visible: showEMA200 });
  }, [showEMA200]);

  const tick = ticks[selectedSymbol];
  const isJpy = selectedSymbol.includes('JPY');
  const priceDecimals = isJpy ? 3 : 5;

  return (
    <div className="flex flex-col h-full bg-card border border-border rounded-lg overflow-hidden">
      {/* Chart toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-card/50 gap-2 flex-wrap">
        {/* Symbol selector */}
        <div className="relative">
          <button
            onClick={() => setShowSymbolMenu((s) => !s)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-muted hover:bg-muted/80 text-sm font-semibold text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-haspopup="listbox"
            aria-expanded={showSymbolMenu}
          >
            {selectedSymbol}
            <ChevronDown className="w-3 h-3 text-muted-foreground" aria-hidden />
          </button>

          {showSymbolMenu && (
            <div
              className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-2xl z-50 py-1 min-w-[120px]"
              role="listbox"
              aria-label="Select trading pair"
            >
              {SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  role="option"
                  aria-selected={sym === selectedSymbol}
                  onClick={() => {
                    setSelectedSymbol(sym);
                    setShowSymbolMenu(false);
                  }}
                  className={cn(
                    'w-full text-left px-3 py-2 text-xs font-mono hover:bg-muted transition-colors',
                    sym === selectedSymbol ? 'text-primary bg-primary/10' : 'text-foreground'
                  )}
                >
                  {sym}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Live price */}
        {tick && (
          <div className="flex items-center gap-3">
            <span className="font-mono text-base font-bold text-foreground tabular-nums">
              {tick.bid.toFixed(priceDecimals)}
            </span>
            <span className="text-xs text-muted-foreground font-mono tabular-nums">
              /{tick.ask.toFixed(priceDecimals)}
            </span>
            <span className="text-xs text-muted-foreground">
              Spr: {(tick.spread * (isJpy ? 100 : 10000)).toFixed(1)}
            </span>
          </div>
        )}

        {/* Timeframe selector */}
        <div className="flex items-center gap-1" role="group" aria-label="Select timeframe">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setSelectedTimeframe(tf)}
              className={cn(
                'px-2 py-1 rounded text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selectedTimeframe === tf
                  ? 'bg-primary/20 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              )}
              aria-pressed={selectedTimeframe === tf}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* EMA toggles */}
        <div className="flex items-center gap-1" role="group" aria-label="EMA overlays">
          <button
            onClick={() => setShowEMA20((s) => !s)}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              showEMA20
                ? 'bg-yellow-500/20 text-yellow-400'
                : 'text-muted-foreground hover:bg-muted'
            )}
            aria-pressed={showEMA20}
          >
            EMA20
          </button>
          <button
            onClick={() => setShowEMA50((s) => !s)}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              showEMA50
                ? 'bg-purple-500/20 text-purple-400'
                : 'text-muted-foreground hover:bg-muted'
            )}
            aria-pressed={showEMA50}
          >
            EMA50
          </button>
          <button
            onClick={() => setShowEMA200((s) => !s)}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              showEMA200
                ? 'bg-pink-500/20 text-pink-400'
                : 'text-muted-foreground hover:bg-muted'
            )}
            aria-pressed={showEMA200}
          >
            EMA200
          </button>
        </div>
      </div>

      {/* Chart area */}
      <div className="flex-1 relative" style={{ minHeight: 0 }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
            <div className="flex flex-col items-center gap-2">
              <div
                className="w-6 h-6 rounded-full border-2 border-muted border-t-primary animate-spin"
              />
              <span className="text-xs text-muted-foreground">Loading chart...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
