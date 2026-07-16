'use client';
import { useTheme } from 'next-themes';
import Link from 'next/link';
import { Sun, Moon, Bell, LogOut, User, ChevronDown, Wifi, WifiOff, Search, Settings, ShieldCheck, Sparkles } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@radix-ui/react-dropdown-menu';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/cn';
import { useAuthStore } from '@/lib/store/authStore';
import { useRiskStore } from '@/lib/store/riskStore';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useWSStatus } from '@/lib/websocket';
import { formatCurrency, formatPnL } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { api } from '@/lib/api';
import { AnimatedNumber } from '@/components/effects/AnimatedNumber';
import { useRouter } from 'next/navigation';

interface TopBarProps {
  sidebarCollapsed: boolean;
}

export function TopBar({ sidebarCollapsed }: TopBarProps) {
  const { theme, setTheme } = useTheme();
  const { user, clearAuth } = useAuthStore();
  const wsStatus = useWSStatus();
  const account = useTradingStore((s) => s.account);
  const unacknowledgedAlerts = useRiskStore((s) => s.unacknowledgedCount);
  const router = useRouter();

  const handleLogout = async () => {
    await api.auth.logout();
    clearAuth();
    router.push('/login');
  };

  const balance = account?.balance ?? 125_430.5;
  const dayPnl = account?.day_pnl ?? 2340.5;
  const equity = account?.equity ?? 126_842.3;

  return (
    <header
      className="fixed top-0 right-0 z-10 h-[60px] border-b border-border bg-card/95 backdrop-blur-sm flex items-center px-4 gap-4"
      style={{ left: sidebarCollapsed ? 64 : 220, transition: 'left 0.2s ease-in-out' }}
    >
      {/* Gradient accent line */}
      <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-primary via-accent to-transparent" />
      {/* Account metrics */}
      <div className="flex items-center gap-6 flex-1 min-w-0">
        {/* Balance */}
        <div className="hidden sm:block">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider leading-none mb-0.5">Balance</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">
            <AnimatedNumber value={balance} prefix="$" />
          </div>
        </div>

        <div className="w-px h-6 bg-border" />

        {/* Equity */}
        <div className="hidden md:block">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider leading-none mb-0.5">Equity</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">
            <AnimatedNumber value={equity} prefix="$" />
          </div>
        </div>

        <div className="w-px h-6 bg-border hidden md:block" />

        {/* Day P&L */}
        <div className="hidden sm:block">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider leading-none mb-0.5">Day P&L</div>
          <div className={cn('font-mono text-sm font-semibold tabular-nums', getPnLColor(dayPnl))}>
            <AnimatedNumber value={dayPnl} formatter={(v) => formatPnL(v)} />
          </div>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        {/* Connection status */}
        <div
          className={cn(
            'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
            wsStatus === 'connected'
              ? 'bg-profit/10 text-profit'
              : 'bg-loss/10 text-loss'
          )}
          role="status"
          aria-live="polite"
          aria-label={`WebSocket ${wsStatus}`}
        >
          {wsStatus === 'connected' ? (
            <Wifi className="w-3 h-3" aria-hidden />
          ) : (
            <WifiOff className="w-3 h-3" aria-hidden />
          )}
          <span className="hidden sm:inline font-medium">
            {wsStatus === 'connected' ? 'Live' : 'Offline'}
          </span>
        </div>

        {/* Command palette trigger */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('open-command-palette'))}
          className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-muted hover:bg-muted/80 text-xs text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Open command palette"
        >
          <Search className="w-3 h-3" aria-hidden />
          <span>Search</span>
          <kbd className="font-mono bg-background/50 px-1.5 py-0.5 rounded text-[10px] border border-border">⌘K</kbd>
        </button>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="w-8 h-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? (
            <Sun className="w-4 h-4" aria-hidden />
          ) : (
            <Moon className="w-4 h-4" aria-hidden />
          )}
        </button>

        {/* Notifications */}
        <button
          onClick={() => {
            toast.dismiss();
            const alerts = useRiskStore.getState().alerts;
            if (alerts.length === 0) {
              toast.info('No new notifications', { duration: 2000 });
            } else {
              toast.message(`${alerts.length} unread alert(s)`, {
                description: alerts[alerts.length - 1]?.message,
                duration: 3000,
              });
            }
          }}
          className="relative w-8 h-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Notifications ${unacknowledgedAlerts > 0 ? `(${unacknowledgedAlerts} unread)` : ''}`}
        >
          <Bell className="w-4 h-4" aria-hidden />
          {unacknowledgedAlerts > 0 && (
            <span
              className="absolute top-1 right-1 w-2 h-2 bg-loss rounded-full"
              aria-hidden
            />
          )}
        </button>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger
            className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="User menu"
          >
            <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center">
              <User className="w-3 h-3 text-primary" aria-hidden />
            </div>
            <span className="text-sm text-foreground hidden sm:block max-w-[100px] truncate">
              {user?.username ?? 'demo'}
            </span>
            <ChevronDown className="w-3 h-3 text-muted-foreground" aria-hidden />
          </DropdownMenuTrigger>

          <DropdownMenuContent
            align="end"
            sideOffset={8}
            className="w-48 bg-card border border-border rounded-lg shadow-2xl p-1 z-50"
          >
            <div className="px-3 py-2 mb-1">
              <p className="text-sm font-medium text-foreground">{user?.full_name ?? 'Demo Trader'}</p>
              <p className="text-xs text-muted-foreground truncate">{user?.email ?? 'demo@forexbot.ai'}</p>
            </div>
            <DropdownMenuSeparator className="border-border mx-1 my-1" />
            {user?.role && ['admin', 'superadmin'].includes(user.role) && (
              <DropdownMenuItem asChild>
                <Link href="/admin" className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted/50 rounded-md cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <ShieldCheck className="w-4 h-4" aria-hidden />
                  Admin Panel
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuItem asChild>
              <Link href="/settings" className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted/50 rounded-md cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Settings className="w-4 h-4" aria-hidden />
                Settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-2 text-sm text-loss hover:bg-loss/10 rounded-md cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <LogOut className="w-4 h-4" aria-hidden />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
