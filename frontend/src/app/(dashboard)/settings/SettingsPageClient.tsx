'use client';
import { useTheme } from 'next-themes';
import { useAuthStore } from '@/lib/store/authStore';
import { cn } from '@/lib/utils/cn';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h2 className="text-sm font-semibold text-foreground mb-4">{title}</h2>
      {children}
    </div>
  );
}

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
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

export function SettingsPageClient() {
  const { theme, setTheme } = useTheme();
  const user = useAuthStore((s) => s.user);

  return (
    <div className="space-y-4 max-w-2xl animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground">Platform configuration and preferences</p>
      </div>

      {/* Account */}
      <Section title="Account">
        <SettingRow label="Username" description="Your login identifier">
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
          <span
            className={cn(
              'text-xs font-medium px-2 py-0.5 rounded',
              user?.mfa_enabled
                ? 'bg-profit/10 text-profit'
                : 'bg-muted text-muted-foreground'
            )}
          >
            {user?.mfa_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </SettingRow>
      </Section>

      {/* Appearance */}
      <Section title="Appearance">
        <SettingRow label="Theme" description="Interface color scheme">
          <div className="flex rounded-md overflow-hidden border border-border">
            {['dark', 'light'].map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className={cn(
                  'px-4 py-1.5 text-xs font-medium transition-colors capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  theme === t
                    ? 'bg-primary/20 text-primary'
                    : 'bg-transparent text-muted-foreground hover:text-foreground'
                )}
                aria-pressed={theme === t}
              >
                {t}
              </button>
            ))}
          </div>
        </SettingRow>
      </Section>

      {/* Data */}
      <Section title="Data & API">
        <SettingRow
          label="Demo Mode"
          description="Using mock data — no live broker connection"
        >
          <span className="text-xs bg-yellow-500/10 text-yellow-400 px-2 py-0.5 rounded font-medium">
            {process.env.NEXT_PUBLIC_DEMO_MODE === 'true' ? 'Active' : 'Inactive'}
          </span>
        </SettingRow>
        <SettingRow label="API URL">
          <span className="text-xs font-mono text-muted-foreground">
            {process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}
          </span>
        </SettingRow>
        <SettingRow label="WebSocket URL">
          <span className="text-xs font-mono text-muted-foreground">
            {process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'}
          </span>
        </SettingRow>
      </Section>
    </div>
  );
}
