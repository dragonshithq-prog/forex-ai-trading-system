'use client';
import { useState, useEffect, useCallback } from 'react';
import { Search, ArrowUpRight, ArrowDownRight, Command } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { useRouter } from 'next/navigation';

interface CommandAction {
  id: string;
  label: string;
  description?: string;
  shortcut?: string;
  action: () => void;
  category: 'navigation' | 'trading' | 'chart' | 'system';
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const router = useRouter();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener('open-command-palette', handler);
    return () => window.removeEventListener('open-command-palette', handler);
  }, []);

  const actions: CommandAction[] = [
    { id: 'nav-dashboard', label: 'Go to Dashboard', description: 'Main trading dashboard', shortcut: 'G D', category: 'navigation', action: () => { router.push('/dashboard'); setOpen(false); } },
    { id: 'nav-positions', label: 'Go to Positions', description: 'View open positions', shortcut: 'G P', category: 'navigation', action: () => { router.push('/positions'); setOpen(false); } },
    { id: 'nav-orders', label: 'Go to Orders', description: 'Order history', shortcut: 'G O', category: 'navigation', action: () => { router.push('/orders'); setOpen(false); } },
    { id: 'nav-analytics', label: 'Go to Analytics', description: 'Performance analytics', shortcut: 'G A', category: 'navigation', action: () => { router.push('/analytics'); setOpen(false); } },
    { id: 'nav-backtest', label: 'Go to Backtest', description: 'Strategy testing', shortcut: 'G B', category: 'navigation', action: () => { router.push('/backtest'); setOpen(false); } },
    { id: 'nav-risk', label: 'Go to Risk', description: 'Risk management', shortcut: 'G R', category: 'navigation', action: () => { router.push('/risk'); setOpen(false); } },
    { id: 'nav-journal', label: 'Go to Journal', description: 'Trade journal', shortcut: 'G J', category: 'navigation', action: () => { router.push('/journal'); setOpen(false); } },
    { id: 'nav-settings', label: 'Go to Settings', description: 'Platform settings', shortcut: 'G S', category: 'navigation', action: () => { router.push('/settings'); setOpen(false); } },
    { id: 'chart-candles', label: 'Switch to Candles', description: 'Change chart style to candles', category: 'chart', action: () => { window.dispatchEvent(new CustomEvent('chart-style', { detail: 'candles' })); setOpen(false); } },
    { id: 'chart-bars', label: 'Switch to Bars', description: 'Change chart style to bars', category: 'chart', action: () => { window.dispatchEvent(new CustomEvent('chart-style', { detail: 'bars' })); setOpen(false); } },
    { id: 'chart-line', label: 'Switch to Line', description: 'Change chart style to line', category: 'chart', action: () => { window.dispatchEvent(new CustomEvent('chart-style', { detail: 'line' })); setOpen(false); } },
    { id: 'toggle-theme', label: 'Toggle Theme', description: 'Switch between dark and light', shortcut: 'T', category: 'system', action: () => { window.dispatchEvent(new CustomEvent('toggle-theme')); setOpen(false); } },
  ];

  const filtered = query
    ? actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()) || a.category.includes(query.toLowerCase()))
    : actions;

  const grouped = filtered.reduce<Record<string, CommandAction[]>>((acc, action) => {
    if (!acc[action.category]) acc[action.category] = [];
    acc[action.category].push(action);
    return acc;
  }, {});

  const categoryLabels: Record<string, string> = {
    navigation: 'Navigation',
    trading: 'Trading',
    chart: 'Chart',
    system: 'System',
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-start justify-center pt-[20vh]">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted text-[10px] text-muted-foreground font-mono">
            <Command className="w-3 h-3" /> K
          </kbd>
        </div>

        <div className="max-h-[50vh] overflow-y-auto p-2 scrollbar-hidden">
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="mb-2">
              <div className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                {categoryLabels[category] ?? category}
              </div>
              {items.map((action) => (
                <button
                  key={action.id}
                  onClick={action.action}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-foreground hover:bg-muted transition-colors text-left group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{action.label}</div>
                    {action.description && (
                      <div className="text-xs text-muted-foreground mt-0.5">{action.description}</div>
                    )}
                  </div>
                  {action.shortcut && (
                    <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/60 text-[10px] text-muted-foreground font-mono opacity-0 group-hover:opacity-100 transition-opacity">
                      {action.shortcut}
                    </kbd>
                  )}
                </button>
              ))}
            </div>
          ))}

          {filtered.length === 0 && (
            <div className="text-center py-8 text-sm text-muted-foreground">
              No results for &ldquo;{query}&rdquo;
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-border bg-muted/20">
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1"><kbd className="font-mono bg-muted px-1 rounded">↑↓</kbd> Navigate</span>
            <span className="flex items-center gap-1"><kbd className="font-mono bg-muted px-1 rounded">↵</kbd> Select</span>
            <span className="flex items-center gap-1"><kbd className="font-mono bg-muted px-1 rounded">esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
