'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { createChart, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, BarData, LineData, UTCTimestamp } from 'lightweight-charts';
import { useMarketStore } from '@/lib/store/marketStore';
import { useMarketData } from '@/lib/hooks/useMarketData';
import { cn } from '@/lib/utils/cn';
import { ChevronDown, Expand, Minimize, RotateCw, TrendingUp, BarChart3, Activity } from 'lucide-react';

const SYMBOLS = ['EURUSD', 'GBPUSD', 'GBPJPY', 'USDJPY', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'EURJPY', 'GBPCHF', 'EURAUD', 'GBPNZD'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1'] as const;
type ChartStyle = 'candles' | 'bars' | 'line';

const EMA_COLORS = { ema9: '#22c55e', ema20: '#f59e0b', ema50: '#8b5cf6', ema200: '#ec4899' };
const BB_COLORS = { upper: 'rgba(59,130,246,0.3)', middle: 'rgba(59,130,246,0.6)', lower: 'rgba(59,130,246,0.3)' };

function calcEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1); const result: number[] = []; let ema = data[0];
  for (let i = 0; i < data.length; i++) { ema = i === 0 ? data[0] : data[i] * k + ema * (1 - k); result.push(ema); }
  return result;
}

function calcSMA(data: number[], period: number): number[] {
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(data[i]); continue; }
    let sum = 0; for (let j = i - period + 1; j <= i; j++) sum += data[j];
    result.push(sum / period);
  }
  return result;
}

function calcStdDev(data: number[], period: number, sma: number[]): number[] {
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(0); continue; }
    let sumSq = 0; for (let j = i - period + 1; j <= i; j++) sumSq += (data[j] - sma[i]) ** 2;
    result.push(Math.sqrt(sumSq / period));
  }
  return result;
}

function calcRSI(data: number[], period: number = 14): number[] {
  const result: number[] = []; let gains = 0, losses = 0;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) { result.push(50); continue; }
    const diff = data[i] - data[i - 1];
    const gain = diff > 0 ? diff : 0; const loss = diff < 0 ? -diff : 0;
    if (i < period) { gains += gain; losses += loss; result.push(50); }
    else if (i === period) {
      gains = (gains + gain) / period; losses = (losses + loss) / period;
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
  const indicatorSeriesRef = useRef<Record<string, ISeriesApi<'Line'> | undefined>>({});
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const chartInited = useRef(false);

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
  const [isFullscreen, setIsFullscreen] = useState(false);

  const { candles, isLoading } = useMarketData(selectedSymbol, selectedTimeframe);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current || chartInited.current) return;
    chartInited.current = true;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { color: 'transparent' }, textColor: '#a1a1aa', fontFamily: 'var(--font-inter), system-ui, sans-serif', fontSize: 11 },
      grid: { vertLines: { color: '#1c1c1c' }, horzLines: { color: '#1c1c1c' } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#444', width: 1, style: 3, labelBackgroundColor: '#333' }, horzLine: { color: '#444', width: 1, style: 3, labelBackgroundColor: '#333' } },
      rightPriceScale: { borderColor: '#222', scaleMargins: { top: 0.08, bottom: 0.25 } },
      timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });

    candleSeriesRef.current = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444', wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });

    barSeriesRef.current = chart.addBarSeries({ upColor: '#22c55e', downColor: '#ef4444', thinBars: false });

    lineSeriesRef.current = chart.addLineSeries({ color: '#3b82f6', lineWidth: 2, crosshairMarkerVisible: true });

    barSeriesRef.current.applyOptions({ visible: false });
    lineSeriesRef.current.applyOptions({ visible: false });

    volumeSeriesRef.current = chart.addHistogramSeries({
      priceFormat: { type: 'volume' }, priceScaleId: 'volume', color: 'rgba(59,130,246,0.25)',
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const indicators = ['ema9', 'ema20', 'ema50', 'ema200', 'bbUpper', 'bbMiddle', 'bbLower'] as const;
    const indicatorConfig: Record<string, { color: string; title: string; visible: boolean }> = {
      ema9: { color: EMA_COLORS.ema9, title: 'EMA 9', visible: false },
      ema20: { color: EMA_COLORS.ema20, title: 'EMA 20', visible: true },
      ema50: { color: EMA_COLORS.ema50, title: 'EMA 50', visible: true },
      ema200: { color: EMA_COLORS.ema200, title: 'EMA 200', visible: true },
      bbUpper: { color: BB_COLORS.upper, title: 'BB Upper', visible: false },
      bbMiddle: { color: BB_COLORS.middle, title: 'BB Mid', visible: false },
      bbLower: { color: BB_COLORS.lower, title: 'BB Lower', visible: false },
    };

    for (const key of indicators) {
      const cfg = indicatorConfig[key];
      indicatorSeriesRef.current[key] = chart.addLineSeries({ color: cfg.color, lineWidth: 1, title: cfg.title, visible: cfg.visible });
    }

    rsiSeriesRef.current = chart.addLineSeries({
      color: '#8b5cf6', lineWidth: 1, title: 'RSI', visible: false,
      priceScaleId: 'rsi',
    });
    chart.priceScale('rsi').applyOptions({ scaleMargins: { top: 0.7, bottom: 0.3 }, visible: false });

    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.resize(chartContainerRef.current.clientWidth, chartContainerRef.current.clientHeight);
      }
    });
    ro.observe(chartContainerRef.current);
    resizeObserverRef.current = ro;

    return () => {
      resizeObserverRef.current?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      chartInited.current = false;
    };
  }, []);

  // Switch chart style
  const updateChartStyle = useCallback((style: ChartStyle) => {
    setChartStyle(style);
    if (!chartRef.current) return;
    const showCandle = style === 'candles';
    const showBar = style === 'bars';
    const showLine = style === 'line';
    candleSeriesRef.current?.applyOptions({ visible: showCandle });
    barSeriesRef.current?.applyOptions({ visible: showBar });
    lineSeriesRef.current?.applyOptions({ visible: showLine });
    chartRef.current?.timeScale().fitContent();
  }, []);

  // Update data when candles change
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const barSeries = barSeriesRef.current;
    const lineSeries = lineSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !candles.length) return;

    const times: UTCTimestamp[] = [];
    const candleData: CandlestickData[] = [];
    const barData: BarData[] = [];
    const lineData: LineData[] = [];
    const volumeData: { time: UTCTimestamp; value: number; color: string }[] = [];
    const closes: number[] = [];

    for (const c of candles) {
      const time = (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp;
      times.push(time);
      candleData.push({ time, open: c.open, high: c.high, low: c.low, close: c.close });
      barData.push({ time, open: c.open, high: c.high, low: c.low, close: c.close });
      lineData.push({ time, value: c.close });
      volumeData.push({ time, value: c.volume, color: c.close >= c.open ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)' });
      closes.push(c.close);
    }

    candleSeries.setData(candleData);
    barSeries?.setData(barData);
    lineSeries?.setData(lineData);
    volumeSeries?.setData(volumeData);

    const setLineData = (key: string, values: number[]) => {
      const s = indicatorSeriesRef.current[key];
      if (s) s.setData(values.map((v, i) => ({ time: times[i], value: v })));
    };

    setLineData('ema9', calcEMA(closes, 9));
    setLineData('ema20', calcEMA(closes, 20));
    setLineData('ema50', calcEMA(closes, 50));
    setLineData('ema200', calcEMA(closes, 200));

    if (showBB) {
      const sma20 = calcSMA(closes, 20);
      const stdDev = calcStdDev(closes, 20, sma20);
      setLineData('bbMiddle', sma20);
      setLineData('bbUpper', sma20.map((v, i) => v + 2 * stdDev[i]));
      setLineData('bbLower', sma20.map((v, i) => v - 2 * stdDev[i]));
    }

    if (showRSI && rsiSeriesRef.current) {
      rsiSeriesRef.current.setData(calcRSI(closes, 14).map((v, i) => ({ time: times[i], value: v })));
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, showBB, showRSI]);

  // Live tick update
  useEffect(() => {
    const tick = ticks[selectedSymbol];
    if (!tick || !candleSeriesRef.current || !candles.length) return;
    const last = candles[candles.length - 1];
    if (!last) return;
    const time = (new Date(last.timestamp).getTime() / 1000) as UTCTimestamp;
    candleSeriesRef.current.update({ time, open: last.open, high: Math.max(last.high, tick.bid), low: Math.min(last.low, tick.bid), close: tick.bid });
  }, [ticks, selectedSymbol, candles]);

  // Listen for external chart style changes (command palette, watchlist)
  const updateChartStyleRef = useRef(updateChartStyle);
  updateChartStyleRef.current = updateChartStyle;

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<ChartStyle>;
      if (custom.detail && ['candles', 'bars', 'line'].includes(custom.detail)) {
        updateChartStyleRef.current(custom.detail);
      }
    };
    window.addEventListener('chart-style', handler as EventListener);
    return () => window.removeEventListener('chart-style', handler as EventListener);
  }, []);

  // Indicator visibility toggles
  useEffect(() => {
    indicatorSeriesRef.current['ema9']?.applyOptions({ visible: showEMA9 });
  }, [showEMA9]);
  useEffect(() => {
    indicatorSeriesRef.current['ema20']?.applyOptions({ visible: showEMA20 });
  }, [showEMA20]);
  useEffect(() => {
    indicatorSeriesRef.current['ema50']?.applyOptions({ visible: showEMA50 });
  }, [showEMA50]);
  useEffect(() => {
    indicatorSeriesRef.current['ema200']?.applyOptions({ visible: showEMA200 });
  }, [showEMA200]);
  useEffect(() => {
    ['bbUpper', 'bbMiddle', 'bbLower'].forEach((k) => indicatorSeriesRef.current[k]?.applyOptions({ visible: showBB }));
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
    if (!document.fullscreenElement) { el.requestFullscreen?.(); setIsFullscreen(true); }
    else { document.exitFullscreen?.(); setIsFullscreen(false); }
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
        {/* Symbol selector */}
        <div className="relative">
          <button onClick={() => setShowSymbolMenu((s) => !s)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-muted hover:bg-muted/80 text-sm font-semibold text-foreground transition-colors">
            {selectedSymbol} <ChevronDown className="w-3 h-3 text-muted-foreground" />
          </button>
          {showSymbolMenu && (
            <div className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-2xl z-50 py-1 min-w-[120px] max-h-[240px] overflow-y-auto" role="listbox">
              {SYMBOLS.map((sym) => (
                <button key={sym} role="option" aria-selected={sym === selectedSymbol}
                  onClick={() => { setSelectedSymbol(sym); setShowSymbolMenu(false); }}
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
              className={cn('px-1.5 py-1 rounded text-[10px] font-medium transition-colors', selectedTimeframe === tf ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted')}>
              {tf}
            </button>
          ))}
        </div>

        {/* Chart style toggle */}
        <div className="flex items-center gap-0.5">
          {(['candles', 'bars', 'line'] as const).map((style) => (
            <button key={style} onClick={() => updateChartStyle(style)}
              className={cn('px-1.5 py-1 rounded text-[10px] font-medium transition-colors', chartStyle === style ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted')}
              title={style.charAt(0).toUpperCase() + style.slice(1)}>
              {style === 'candles' ? 'Cdl' : style === 'bars' ? 'Bar' : 'Line'}
            </button>
          ))}
          <span className="w-px h-3 bg-border mx-1" />
          <button onClick={toggleFullscreen} className="px-1.5 py-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
            {isFullscreen ? <Minimize className="w-3.5 h-3.5" /> : <Expand className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Indicator toggles */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border/50 bg-surface/50 flex-wrap">
        <IndBtn label="EMA9" active={showEMA9} color="green" onClick={() => setShowEMA9((s) => !s)} />
        <IndBtn label="EMA20" active={showEMA20} color="yellow" onClick={() => setShowEMA20((s) => !s)} />
        <IndBtn label="EMA50" active={showEMA50} color="purple" onClick={() => setShowEMA50((s) => !s)} />
        <IndBtn label="EMA200" active={showEMA200} color="pink" onClick={() => setShowEMA200((s) => !s)} />
        <span className="w-px h-3 bg-border mx-0.5" />
        <IndBtn label="BB" active={showBB} color="blue" onClick={() => setShowBB((s) => !s)} />
        <IndBtn label="RSI" active={showRSI} color="violet" onClick={() => setShowRSI((s) => !s)} />
        <IndBtn label="Vol" active={showVolume} color="primary" onClick={() => setShowVolume((s) => !s)} />
      </div>

      {/* Chart area */}
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

function IndBtn({ label, active, color, onClick }: { label: string; active: boolean; color: string; onClick: () => void }) {
  const colorMap: Record<string, string> = {
    green: 'bg-green-500/20 text-green-400', yellow: 'bg-yellow-500/20 text-yellow-400',
    purple: 'bg-purple-500/20 text-purple-400', pink: 'bg-pink-500/20 text-pink-400',
    blue: 'bg-blue-500/20 text-blue-400', violet: 'bg-violet-500/20 text-violet-400',
    primary: 'bg-primary/20 text-primary',
  };
  return (
    <button onClick={onClick}
      className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors', active ? colorMap[color] || colorMap.primary : 'text-muted-foreground hover:bg-muted')}>
      {label}
    </button>
  );
}

export default dynamic(() => Promise.resolve({ default: TradingChart }), { ssr: false });