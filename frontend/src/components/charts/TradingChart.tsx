'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import type { IChartApi, ISeriesApi, CandlestickData, UTCTimestamp, LineStyle, LineData, HistogramData } from 'lightweight-charts';
import { useMarketStore } from '@/lib/store/marketStore';
import { useMarketData } from '@/lib/hooks/useMarketData';
import { cn } from '@/lib/utils/cn';
import { ChevronDown, Expand, Minimize, RotateCw, TrendingUp, BarChart3, Activity } from 'lucide-react';

const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'EURJPY', 'GBPCHF', 'EURAUD', 'GBPNZD'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1'] as const;
type ChartStyle = 'candles' | 'bars' | 'line';

const EMA_COLORS = {
  ema9: '#22c55e',
  ema20: '#f59e0b',
  ema50: '#8b5cf6',
  ema200: '#ec4899',
} as const;

const BB_COLORS = {
  upper: 'rgba(59,130,246,0.3)',
  middle: 'rgba(59,130,246,0.6)',
  lower: 'rgba(59,130,246,0.3)',
} as const;

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

function calcSMA(data: number[], period: number): number[] {
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(data[i]); continue; }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j];
    result.push(sum / period);
  }
  return result;
}

function calcStdDev(data: number[], period: number, sma: number[]): number[] {
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(0); continue; }
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) sumSq += (data[j] - sma[i]) ** 2;
    result.push(Math.sqrt(sumSq / period));
  }
  return result;
}

function calcRSI(data: number[], period: number = 14): number[] {
  const result: number[] = [];
  let gains = 0, losses = 0;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) { result.push(50); continue; }
    const diff = data[i] - data[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    if (i < period) {
      gains += gain;
      losses += loss;
      result.push(50);
    } else if (i === period) {
      gains = (gains + gain) / period;
      losses = (losses + loss) / period;
      const rs = losses === 0 ? 100 : gains / losses;
      result.push(100 - 100 / (1 + rs));
    } else {
      gains = (gains * (period - 1) + gain) / period;
      losses = (losses * (period - 1) + loss) / period;
      const rs = losses === 0 ? 100 : gains / losses;
      result.push(100 - 100 / (1 + rs));
    }
  }
  return result;
}

export function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const barSeriesRef = useRef<ISeriesApi<'Bar'> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const indicatorSeriesRef = useRef<{
    ema9?: ISeriesApi<'Line'>; ema20?: ISeriesApi<'Line'>;
    ema50?: ISeriesApi<'Line'>; ema200?: ISeriesApi<'Line'>;
    bbUpper?: ISeriesApi<'Line'>; bbMiddle?: ISeriesApi<'Line'>; bbLower?: ISeriesApi<'Line'>;
  }>({});
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const selectedTimeframe = useMarketStore((s) => s.selectedTimeframe);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setSelectedTimeframe = useMarketStore((s) => s.setSelectedTimeframe);
  const ticks = useMarketStore((s) => s.ticks);

  const [chartStyle, setChartStyle] = useState<ChartStyle>('candles');
  const [showEMA9, setShowEMA9] = useState(false);
  const [showEMA20, setShowEMA20] = useState(true);
  const [showEMA50, setShowEMA50] = useState(true);
  const [showEMA200, setShowEMA200] = useState(true);
  const [showBB, setShowBB] = useState(false);
  const [showRSI, setShowRSI] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showSymbolMenu, setShowSymbolMenu] = useState(false);
  const [showTimeframeMenu, setShowTimeframeMenu] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const { candles, isLoading } = useMarketData(selectedSymbol, selectedTimeframe);

  useEffect(() => {
    if (!chartContainerRef.current) return;
    import('lightweight-charts').then(({ createChart, CrosshairMode }) => {
      if (!chartContainerRef.current) return;
      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { color: 'transparent' },
          textColor: '#a1a1aa',
          fontFamily: 'var(--font-inter), system-ui, sans-serif',
          fontSize: 11,
        },
        grid: { vertLines: { color: '#1c1c1c' }, horzLines: { color: '#1c1c1c' } },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: { color: '#444', width: 1, style: 3, labelBackgroundColor: '#333' },
          horzLine: { color: '#444', width: 1, style: 3, labelBackgroundColor: '#333' },
        },
        rightPriceScale: { borderColor: '#222', scaleMargins: { top: 0.08, bottom: 0.25 } },
        timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' }, priceScaleId: 'volume', color: 'rgba(59,130,246,0.25)',
      });
      chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

      const ema9 = chart.addLineSeries({ color: EMA_COLORS.ema9, lineWidth: 1, title: 'EMA 9', visible: false });
      const ema20 = chart.addLineSeries({ color: EMA_COLORS.ema20, lineWidth: 1, title: 'EMA 20', visible: true });
      const ema50 = chart.addLineSeries({ color: EMA_COLORS.ema50, lineWidth: 1, title: 'EMA 50', visible: true });
      const ema200 = chart.addLineSeries({ color: EMA_COLORS.ema200, lineWidth: 1, title: 'EMA 200', visible: true });

      const bbUpper = chart.addLineSeries({ color: BB_COLORS.upper, lineWidth: 1, title: 'BB Upper', visible: false });
      const bbMiddle = chart.addLineSeries({ color: BB_COLORS.middle, lineWidth: 1, title: 'BB Mid', visible: false });
      const bbLower = chart.addLineSeries({ color: BB_COLORS.lower, lineWidth: 1, title: 'BB Lower', visible: false });

      const rsiSeries = chart.addLineSeries({
        color: '#8b5cf6', lineWidth: 1, title: 'RSI', visible: false,
        priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(1) },
        priceScaleId: 'rsi',
      });
      chart.priceScale('rsi').applyOptions({ scaleMargins: { top: 0.7, bottom: 0.3 }, visible: false });

      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      volumeSeriesRef.current = volumeSeries;
      rsiSeriesRef.current = rsiSeries;
      indicatorSeriesRef.current = { ema9, ema20, ema50, ema200, bbUpper, bbMiddle, bbLower };

      const ro = new ResizeObserver(() => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.resize(chartContainerRef.current.clientWidth, chartContainerRef.current.clientHeight);
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
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return;
    const candleData: CandlestickData[] = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    const closes = candles.map((c) => c.close);
    const times = candles.map((c) => (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp);
    const volumes = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)',
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current?.setData(volumes);

    const setLineData = (ref: ISeriesApi<'Line'> | undefined, values: number[]) => {
      if (!ref) return;
      ref.setData(values.map((v, i) => ({ time: times[i], value: v })));
    };

    setLineData(indicatorSeriesRef.current.ema9, calcEMA(closes, 9));
    setLineData(indicatorSeriesRef.current.ema20, calcEMA(closes, 20));
    setLineData(indicatorSeriesRef.current.ema50, calcEMA(closes, 50));
    setLineData(indicatorSeriesRef.current.ema200, calcEMA(closes, 200));

    if (showBB) {
      const sma20 = calcSMA(closes, 20);
      const stdDev = calcStdDev(closes, 20, sma20);
      setLineData(indicatorSeriesRef.current.bbMiddle, sma20);
      setLineData(indicatorSeriesRef.current.bbUpper, sma20.map((v, i) => v + 2 * stdDev[i]));
      setLineData(indicatorSeriesRef.current.bbLower, sma20.map((v, i) => v - 2 * stdDev[i]));
    }

    if (showRSI && rsiSeriesRef.current) {
      const rsiData = calcRSI(closes, 14);
      rsiSeriesRef.current.setData(rsiData.map((v, i) => ({ time: times[i], value: v })));
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, showBB, showRSI]);

  useEffect(() => {
    const tick = ticks[selectedSymbol];
    if (!tick || !candleSeriesRef.current || !candles.length) return;
    const last = candles[candles.length - 1];
    if (!last) return;
    const time = (new Date(last.timestamp).getTime() / 1000) as UTCTimestamp;
    candleSeriesRef.current.update({ time, open: last.open, high: Math.max(last.high, tick.bid), low: Math.min(last.low, tick.bid), close: tick.bid });
  }, [ticks, selectedSymbol, candles]);

  useEffect(() => { indicatorSeriesRef.current.ema9?.applyOptions({ visible: showEMA9 }); }, [showEMA9]);
  useEffect(() => { indicatorSeriesRef.current.ema20?.applyOptions({ visible: showEMA20 }); }, [showEMA20]);
  useEffect(() => { indicatorSeriesRef.current.ema50?.applyOptions({ visible: showEMA50 }); }, [showEMA50]);
  useEffect(() => { indicatorSeriesRef.current.ema200?.applyOptions({ visible: showEMA200 }); }, [showEMA200]);
  useEffect(() => {
    indicatorSeriesRef.current.bbUpper?.applyOptions({ visible: showBB });
    indicatorSeriesRef.current.bbMiddle?.applyOptions({ visible: showBB });
    indicatorSeriesRef.current.bbLower?.applyOptions({ visible: showBB });
  }, [showBB]);
  useEffect(() => {
    rsiSeriesRef.current?.applyOptions({ visible: showRSI });
    chartRef.current?.priceScale('rsi').applyOptions({ visible: showRSI });
  }, [showRSI]);
  useEffect(() => {
    volumeSeriesRef.current?.applyOptions({ visible: showVolume });
    chartRef.current?.priceScale('volume').applyOptions({ visible: showVolume });
  }, [showVolume]);

  const toggleFullscreen = useCallback(() => {
    const el = chartContainerRef.current?.parentElement;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  }, []);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const tick = ticks[selectedSymbol];
  const isJpy = selectedSymbol.includes('JPY');
  const priceDecimals = isJpy ? 3 : 5;

  return (
    <div className={cn('flex flex-col bg-card border border-border rounded-lg overflow-hidden', isFullscreen && 'fixed inset-0 z-[9999] rounded-none')}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-card/50 gap-2 flex-wrap">
        {/* Symbol */}
        <div className="relative">
          <button onClick={() => setShowSymbolMenu((s) => !s)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-muted hover:bg-muted/80 text-sm font-semibold text-foreground transition-colors">
            {selectedSymbol} <ChevronDown className="w-3 h-3 text-muted-foreground" />
          </button>
          {showSymbolMenu && (
            <div className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-2xl z-50 py-1 min-w-[120px] max-h-[240px] overflow-y-auto" role="listbox">
              {SYMBOLS.map((sym) => (
                <button key={sym} role="option" aria-selected={sym === selectedSymbol} onClick={() => { setSelectedSymbol(sym); setShowSymbolMenu(false); }}
                  className={cn('w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-muted transition-colors', sym === selectedSymbol ? 'text-primary bg-primary/10' : 'text-foreground')}>
                  {sym}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Live price */}
        {tick && (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-foreground tabular-nums">{tick.bid.toFixed(priceDecimals)}</span>
            <span className="text-xs text-muted-foreground font-mono">/{tick.ask.toFixed(priceDecimals)}</span>
            <span className="text-[10px] text-muted-foreground">Spr: {(tick.spread * (isJpy ? 100 : 10000)).toFixed(1)}</span>
          </div>
        )}

        {/* Timeframes */}
        <div className="flex items-center gap-0.5" role="group">
          {TIMEFRAMES.map((tf) => (
            <button key={tf} onClick={() => setSelectedTimeframe(tf)}
              className={cn('px-1.5 py-1 rounded text-[10px] font-medium transition-colors',
                selectedTimeframe === tf ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted')}>
              {tf}
            </button>
          ))}
        </div>

        {/* Chart style + indicators + fullscreen */}
        <div className="flex items-center gap-1">
          <button onClick={() => setChartStyle(chartStyle === 'candles' ? 'bars' : chartStyle === 'bars' ? 'line' : 'candles')}
            className="px-1.5 py-1 rounded text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" title="Chart Style">
            {chartStyle === 'candles' ? <BarChart3 className="w-3.5 h-3.5" /> : chartStyle === 'bars' ? <Activity className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5" />}
          </button>
          <button onClick={toggleFullscreen}
            className="px-1.5 py-1 rounded text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
            {isFullscreen ? <Minimize className="w-3.5 h-3.5" /> : <Expand className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Indicator toggles */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border/50 bg-surface/50 flex-wrap">
        <button onClick={() => setShowEMA9((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showEMA9 ? 'bg-green-500/20 text-green-400' : 'text-muted-foreground hover:bg-muted')}>EMA9</button>
        <button onClick={() => setShowEMA20((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showEMA20 ? 'bg-yellow-500/20 text-yellow-400' : 'text-muted-foreground hover:bg-muted')}>EMA20</button>
        <button onClick={() => setShowEMA50((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showEMA50 ? 'bg-purple-500/20 text-purple-400' : 'text-muted-foreground hover:bg-muted')}>EMA50</button>
        <button onClick={() => setShowEMA200((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showEMA200 ? 'bg-pink-500/20 text-pink-400' : 'text-muted-foreground hover:bg-muted')}>EMA200</button>
        <span className="w-px h-3 bg-border mx-0.5" />
        <button onClick={() => setShowBB((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showBB ? 'bg-blue-500/20 text-blue-400' : 'text-muted-foreground hover:bg-muted')}>BB</button>
        <button onClick={() => setShowRSI((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showRSI ? 'bg-violet-500/20 text-violet-400' : 'text-muted-foreground hover:bg-muted')}>RSI</button>
        <button onClick={() => setShowVolume((s) => !s)} className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', showVolume ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:bg-muted')}>Vol</button>
      </div>

      {/* Chart */}
      <div ref={chartContainerRef} className={cn(isFullscreen ? 'flex-1' : 'h-[420px]', 'relative')}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
            <RotateCw className="w-5 h-5 text-muted-foreground animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}

export default dynamic(() => Promise.resolve(TradingChart), { ssr: false });