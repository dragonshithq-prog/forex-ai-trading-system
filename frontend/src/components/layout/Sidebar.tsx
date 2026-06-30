'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  TrendingUp,
  FileText,
  BarChart3,
  FlaskConical,
  Shield,
  PlugZap,
  Settings,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Activity,
  Bot,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';

const NAV_ITEMS = [
  {
    href: '/dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
    description: 'Overview & live trading',
  },
  {
    href: '/positions',
    label: 'Positions',
    icon: TrendingUp,
    description: 'Open positions',
  },
  {
    href: '/orders',
    label: 'Orders',
    icon: FileText,
    description: 'Order history',
  },
  {
    href: '/analytics',
    label: 'Analytics',
    icon: BarChart3,
    description: 'Performance analytics',
  },
  {
    href: '/backtest',
    label: 'Backtest',
    icon: FlaskConical,
    description: 'Strategy testing',
  },
  {
    href: '/risk',
    label: 'Risk',
    icon: Shield,
    description: 'Risk management',
  },
  {
    href: '/broker-connections',
    label: 'Brokers',
    icon: PlugZap,
    description: 'Broker connections',
  },
  {
    href: '/journal',
    label: 'Journal',
    icon: BookOpen,
    description: 'Trade journal',
  },
  {
    href: '/settings',
    label: 'Settings',
    icon: Settings,
    description: 'Configuration',
  },
] as const;

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 220 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="relative flex flex-col h-full bg-card border-r border-border z-20 overflow-hidden"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-4 border-b border-border min-h-[60px]">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
          <Bot className="w-4 h-4 text-primary" aria-hidden />
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <div className="text-sm font-semibold text-foreground whitespace-nowrap leading-tight">
                Forex AI
              </div>
              <div className="text-[10px] text-muted-foreground whitespace-nowrap">
                Institutional
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-3 overflow-y-auto scrollbar-hidden">
        <ul className="space-y-0.5 px-2" role="list">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    'group flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors duration-150 relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  )}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {/* Active indicator bar */}
                  {isActive && (
                    <motion.div
                      layoutId="active-indicator"
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-full"
                      transition={{ duration: 0.15 }}
                    />
                  )}

                  <Icon
                    className={cn(
                      'w-4 h-4 flex-shrink-0 transition-colors',
                      isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'
                    )}
                    aria-hidden
                  />

                  <AnimatePresence>
                    {!collapsed && (
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="whitespace-nowrap"
                      >
                        {item.label}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Status indicator */}
      <div className="px-2 pb-2">
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-md bg-muted/50',
            collapsed ? 'justify-center' : ''
          )}
        >
          <Activity className="w-3 h-3 text-profit flex-shrink-0" aria-hidden />
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xs text-muted-foreground whitespace-nowrap"
              >
                System Online
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Collapse toggle button */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-[72px] z-30 w-6 h-6 rounded-full border border-border bg-card flex items-center justify-center hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? (
          <ChevronRight className="w-3 h-3 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronLeft className="w-3 h-3 text-muted-foreground" aria-hidden />
        )}
      </button>
    </motion.aside>
  );
}
