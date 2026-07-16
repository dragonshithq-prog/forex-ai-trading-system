'use client';
import { useState, useEffect } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ParticleBackground } from '@/components/effects/ParticleBackground';
import { PageTransition } from '@/components/effects/PageTransition';
import { TickerTape } from '@/components/effects/TickerTape';
import { AchievementToast } from '@/components/effects/AchievementToast';
import { TradeNotification } from '@/components/effects/TradeNotification';
import { AudioManager } from '@/components/effects/AudioManager';
import { useWSConnection } from '@/lib/websocket';
import { useTradingStore } from '@/lib/store/tradingStore';
import { api } from '@/lib/api';

function DashboardInit() {
  const setAccount = useTradingStore((s) => s.setAccount);

  useEffect(() => {
    api.account.getAccountSummary().then(setAccount).catch(console.error);
  }, [setAccount]);

  useWSConnection();
  return null;
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Global effects */}
      <DashboardInit />
      <ParticleBackground />
      <AudioManager />
      <AchievementToast />
      <TradeNotification />

      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-[1]">
        {/* Top bar */}
        <TopBar sidebarCollapsed={sidebarCollapsed} />

        {/* Ticker tape */}
        <div className="pt-[60px]">
          <TickerTape />
        </div>

        {/* Page content */}
        <main
          className="flex-1 overflow-y-auto"
          id="main-content"
          role="main"
        >
          <PageTransition>
            <div className="p-4 min-h-full">
              {children}
            </div>
          </PageTransition>
        </main>
      </div>
    </div>
  );
}
