'use client';
import { useTheme } from 'next-themes';
import { useState, useEffect } from 'react';
import { useAuthStore } from '@/lib/store/authStore';
import { cn } from '@/lib/utils/cn';
import { THEMES, type ThemeId } from '@/components/layout/ThemeProvider';
import { PlugZap, Key, Server, Trash2, RefreshCw, Check, X, Eye, EyeOff, Plus } from 'lucide-react';

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-lg p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function SettingRow({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border/50 last:border-0">
      <div>
        <p className="text-sm text-foreground">{label}</p>
        {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function ThemeCard({ themeId, name, icon, description, isActive, onClick }: {
  themeId: string; name: string; icon: string; description: string; isActive: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all duration-200 theme-preview',
        isActive
          ? 'border-primary bg-primary/10 shadow-glow'
          : 'border-border hover:border-muted-foreground/30 bg-card'
      )}
    >
      <span className="text-2xl">{icon}</span>
      <span className="text-xs font-semibold text-foreground">{name}</span>
      <span className="text-[10px] text-muted-foreground text-center leading-tight">{description}</span>
      {isActive && (
        <div className="absolute top-2 right-2 w-4 h-4 bg-primary rounded-full flex items-center justify-center">
          <Check className="w-3 h-3 text-white" />
        </div>
      )}
    </button>
  );
}

type BrokerEntry = {
  id: string;
  name: string;
  type: string;
  environment: string;
  status: 'connected' | 'disconnected' | 'error';
  hasCredentials: boolean;
  accountNumber?: string;
};

export function SettingsPageClient() {
  const { theme, setTheme } = useTheme();
  const user = useAuthStore((s) => s.user);
  const [brokers, setBrokers] = useState<BrokerEntry[]>([]);
  const [showAddBroker, setShowAddBroker] = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setBrokers([
      { id: '1', name: 'OANDA Practice', type: 'OANDA', environment: 'practice', status: 'disconnected', hasCredentials: true, accountNumber: '123-456-789' },
      { id: '2', name: 'MT5 Live', type: 'MT5', environment: 'live', status: 'connected', hasCredentials: true, accountNumber: '50001' },
    ]);
  }, []);

  const toggleKeyVisibility = (id: string) => setShowKeys((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className="space-y-6 max-w-3xl animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground">Platform configuration, themes, and broker connections</p>
      </div>

      {/* Theme Selection */}
      <Section title="Theme" description="Choose your interface color scheme">
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {THEMES.map((t) => (
            <ThemeCard
              key={t.id}
              themeId={t.id}
              name={t.name}
              icon={t.icon}
              description={t.description}
              isActive={theme === t.id}
              onClick={() => setTheme(t.id)}
            />
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <div className="w-3 h-3 rounded-full" style={{ background: 'hsl(var(--primary))' }} />
          <span>Accent color: <span className="text-foreground font-mono">hsl(var(--primary))</span></span>
          <div className="w-3 h-3 rounded-full ml-2" style={{ background: 'hsl(var(--profit))' }} />
          <span>Profit: <span className="text-profit font-mono">green</span></span>
          <div className="w-3 h-3 rounded-full ml-2" style={{ background: 'hsl(var(--loss))' }} />
          <span>Loss: <span className="text-loss font-mono">red</span></span>
        </div>
      </Section>

      {/* Account */}
      <Section title="Account">
        <SettingRow label="Username">
          <span className="text-sm font-mono text-muted-foreground">{user?.username ?? 'demo'}</span>
        </SettingRow>
        <SettingRow label="Email">
          <span className="text-sm text-muted-foreground">{user?.email ?? 'demo@forexbot.ai'}</span>
        </SettingRow>
        <SettingRow label="Role">
          <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded capitalize">
            {user?.role ?? 'trader'}
          </span>
        </SettingRow>
        <SettingRow label="MFA" description="Two-factor authentication">
          <span className={cn('text-xs font-medium px-2 py-0.5 rounded', user?.mfa_enabled ? 'bg-profit/10 text-profit' : 'bg-muted text-muted-foreground')}>
            {user?.mfa_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </SettingRow>
      </Section>

      {/* Broker Connections */}
      <Section title="Broker Connections" description="Manage your live broker accounts">
        <div className="space-y-3">
          {brokers.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <PlugZap className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No broker accounts configured</p>
              <p className="text-xs mt-1">Add a broker to start trading with live or demo accounts</p>
            </div>
          ) : (
            brokers.map((broker) => (
              <div key={broker.id} className="flex items-center justify-between p-3 rounded-lg bg-surface border border-border/60">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center',
                    broker.status === 'connected' ? 'bg-profit/15' : broker.status === 'error' ? 'bg-loss/15' : 'bg-muted'
                  )}>
                    <Server className={cn(
                      'w-4 h-4',
                      broker.status === 'connected' ? 'text-profit' : broker.status === 'error' ? 'text-loss' : 'text-muted-foreground'
                    )} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{broker.name}</span>
                      <span className={cn(
                        'text-[10px] font-medium px-1.5 py-0.5 rounded',
                        broker.status === 'connected' ? 'bg-profit/10 text-profit' :
                        broker.status === 'error' ? 'bg-loss/10 text-loss' :
                        'bg-muted text-muted-foreground'
                      )}>
                        {broker.status === 'connected' ? 'Live' : broker.status === 'error' ? 'Error' : 'Offline'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{broker.type}</span>
                      <span>·</span>
                      <span className="capitalize">{broker.environment}</span>
                      {broker.accountNumber && <><span>·</span><span className="font-mono">{broker.accountNumber}</span></>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" title="Test Connection">
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                  <button className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" title="Toggle Credentials Visibility">
                    {showKeys[broker.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                  <button className={cn(
                    'w-7 h-7 rounded flex items-center justify-center transition-colors',
                    broker.status === 'connected'
                      ? 'text-loss hover:bg-loss/10'
                      : 'text-profit hover:bg-profit/10'
                  )} title={broker.status === 'connected' ? 'Disconnect' : 'Connect'}>
                    <PlugZap className="w-3.5 h-3.5" />
                  </button>
                  <button className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-loss hover:bg-loss/10 transition-colors" title="Delete">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <button
          onClick={() => setShowAddBroker(true)}
          className="mt-3 w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground hover:text-foreground hover:border-muted-foreground/30 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Broker Account
        </button>
      </Section>

      {/* Data & API */}
      <Section title="Data & API">
        <SettingRow label="Demo Mode" description="Using simulated market data">
          <span className="text-xs bg-yellow-500/10 text-yellow-400 px-2 py-0.5 rounded font-medium">
            {process.env.NEXT_PUBLIC_DEMO_MODE === 'true' ? 'Active' : 'Inactive'}
          </span>
        </SettingRow>
        <SettingRow label="API URL">
          <span className="text-xs font-mono text-muted-foreground">{process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}</span>
        </SettingRow>
        <SettingRow label="WebSocket URL">
          <span className="text-xs font-mono text-muted-foreground">{process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'}</span>
        </SettingRow>
      </Section>
    </div>
  );
}
