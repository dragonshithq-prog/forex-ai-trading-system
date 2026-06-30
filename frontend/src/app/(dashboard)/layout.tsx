'use client';
import { useState, useEffect } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
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
      {/* Initialize WS + account data */}
      <DashboardInit />

      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <TopBar sidebarCollapsed={sidebarCollapsed} />

        {/* Page content */}
        <main
          className="flex-1 overflow-y-auto pt-[60px]"
          id="main-content"
          role="main"
        >
          <div className="p-4 min-h-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
