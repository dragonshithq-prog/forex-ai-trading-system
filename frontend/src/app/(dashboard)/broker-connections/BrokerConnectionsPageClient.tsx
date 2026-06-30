'use client';
import { useState, useCallback } from 'react';
import { useTheme } from 'next-themes';
import {
  Plug,
  PlugZap,
  Trash2,
  Plus,
  RefreshCw,
  Server,
  Key,
  X,
  CheckCircle2,
  XCircle,
  WifiOff,
  TestTubes,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BrokerType = 'OANDA' | 'MT4' | 'MT5' | 'FXCM' | 'cTrader' | 'IBKR';
type ConnectionStatus = 'connected' | 'disconnected' | 'error';
type Environment = 'practice' | 'live';

interface BrokerAccount {
  id: string;
  accountName: string;
  brokerType: BrokerType;
  accountNumber: string;
  environment: Environment;
  status: ConnectionStatus;
  addedAt: string;
}

interface BrokerFormData {
  accountName: string;
  brokerType: BrokerType;
  accountNumber: string;
  environment: Environment;
  apiKey: string;
  apiSecret: string;
  password: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BROKER_TYPES: BrokerType[] = ['OANDA', 'MT4', 'MT5', 'FXCM', 'cTrader', 'IBKR'];

const BROKER_TYPE_COLORS: Record<BrokerType, string> = {
  OANDA: 'text-blue-400',
  MT4: 'text-green-400',
  MT5: 'text-emerald-400',
  FXCM: 'text-yellow-400',
  cTrader: 'text-cyan-400',
  IBKR: 'text-purple-400',
};

const BROKER_TYPE_BG: Record<BrokerType, string> = {
  OANDA: 'bg-blue-400/10',
  MT4: 'bg-green-400/10',
  MT5: 'bg-emerald-400/10',
  FXCM: 'bg-yellow-400/10',
  cTrader: 'bg-cyan-400/10',
  IBKR: 'bg-purple-400/10',
};

const emptyForm: BrokerFormData = {
  accountName: '',
  brokerType: 'OANDA',
  accountNumber: '',
  environment: 'practice',
  apiKey: '',
  apiSecret: '',
  password: '',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusIcon(status: ConnectionStatus) {
  switch (status) {
    case 'connected':
      return CheckCircle2;
    case 'error':
      return XCircle;
    case 'disconnected':
      return WifiOff;
  }
}

function statusLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'connected':
      return 'Connected';
    case 'error':
      return 'Error';
    case 'disconnected':
      return 'Disconnected';
  }
}

function statusColor(status: ConnectionStatus): string {
  switch (status) {
    case 'connected':
      return 'text-profit';
    case 'error':
      return 'text-loss';
    case 'disconnected':
      return 'text-muted-foreground';
  }
}

function statusBg(status: ConnectionStatus): string {
  switch (status) {
    case 'connected':
      return 'bg-profit/10';
    case 'error':
      return 'bg-loss/10';
    case 'disconnected':
      return 'bg-muted/50';
  }
}

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_BROKERS: BrokerAccount[] = [
  {
    id: 'BRK-001',
    accountName: 'OANDA Practice',
    brokerType: 'OANDA',
    accountNumber: '123-456-789',
    environment: 'practice',
    status: 'connected',
    addedAt: '2024-03-15T10:30:00Z',
  },
  {
    id: 'BRK-002',
    accountName: 'MT5 Live',
    brokerType: 'MT5',
    accountNumber: '50012345',
    environment: 'live',
    status: 'disconnected',
    addedAt: '2024-03-20T14:00:00Z',
  },
  {
    id: 'BRK-003',
    accountName: 'FXCM Demo',
    brokerType: 'FXCM',
    accountNumber: 'D987654',
    environment: 'practice',
    status: 'error',
    addedAt: '2024-04-01T09:15:00Z',
  },
  {
    id: 'BRK-004',
    accountName: 'IBKR Live',
    brokerType: 'IBKR',
    accountNumber: 'U1234567',
    environment: 'live',
    status: 'connected',
    addedAt: '2024-04-10T16:45:00Z',
  },
];

// ---------------------------------------------------------------------------
// Broker Card
// ---------------------------------------------------------------------------

function BrokerCard({
  account,
  onTest,
  onToggle,
  onDelete,
}: {
  account: BrokerAccount;
  onTest: (id: string) => void;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const StatusIcon = statusIcon(account.status);
  const isConnected = account.status === 'connected';

  return (
    <div
      className={cn(
        'bg-card border border-border rounded-lg p-4 transition-colors',
        'hover:border-primary/30'
      )}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: icon + info */}
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div
            className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
              BROKER_TYPE_BG[account.brokerType]
            )}
          >
            <Server className={cn('w-5 h-5', BROKER_TYPE_COLORS[account.brokerType])} aria-hidden />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm text-foreground truncate">
                {account.accountName}
              </span>
              <span
                className={cn(
                  'text-[10px] font-semibold px-1.5 py-0.5 rounded',
                  BROKER_TYPE_BG[account.brokerType],
                  BROKER_TYPE_COLORS[account.brokerType]
                )}
              >
                {account.brokerType}
              </span>
              <span
                className={cn(
                  'text-[10px] font-medium px-1.5 py-0.5 rounded capitalize',
                  account.environment === 'live'
                    ? 'bg-loss/10 text-loss'
                    : 'bg-yellow-500/10 text-yellow-400'
                )}
              >
                {account.environment}
              </span>
            </div>

            <p className="text-xs text-muted-foreground mt-1 font-mono">
              Acc: {account.accountNumber}
            </p>
          </div>
        </div>

        {/* Right: status + actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <div
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium',
              statusBg(account.status),
              statusColor(account.status)
            )}
          >
            <StatusIcon className="w-3 h-3" aria-hidden />
            {statusLabel(account.status)}
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border/50">
        <button
          type="button"
          onClick={() => onTest(account.id)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            'bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
        >
          <RefreshCw className="w-3 h-3" aria-hidden />
          Test
        </button>

        <button
          type="button"
          onClick={() => onToggle(account.id)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            isConnected
              ? 'bg-loss/10 text-loss hover:bg-loss/20'
              : 'bg-profit/10 text-profit hover:bg-profit/20'
          )}
        >
          <PlugZap className="w-3 h-3" aria-hidden />
          {isConnected ? 'Disconnect' : 'Connect'}
        </button>

        <button
          type="button"
          onClick={() => onDelete(account.id)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            'bg-muted text-muted-foreground hover:text-loss hover:bg-loss/10',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            'ml-auto'
          )}
        >
          <Trash2 className="w-3 h-3" aria-hidden />
          Delete
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Broker Modal
// ---------------------------------------------------------------------------

function AddBrokerModal({
  open,
  onClose,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (data: BrokerFormData) => void;
}) {
  const [form, setForm] = useState<BrokerFormData>(emptyForm);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = useCallback(
    <K extends keyof BrokerFormData>(field: K, value: BrokerFormData[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!form.accountName.trim() || !form.accountNumber.trim()) return;
      onAdd(form);
      setForm(emptyForm);
      onClose();
    },
    [form, onAdd, onClose]
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  if (!open) return null;

  const inputClass =
    'w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-colors placeholder:text-muted-foreground/50 font-mono';
  const labelClass = 'block text-xs text-muted-foreground font-medium mb-1.5';
  const selectClass = inputClass;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-broker-title"
    >
      <div
        className={cn(
          'bg-card border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4',
          'max-h-[90vh] overflow-y-auto'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
              <Plus className="w-4 h-4 text-primary" aria-hidden />
            </div>
            <h2 id="add-broker-title" className="text-sm font-semibold text-foreground">
              Add Broker Connection
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" aria-hidden />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4" noValidate>
          {/* Row: Account Name */}
          <div>
            <label htmlFor="brk-name" className={labelClass}>
              Account Name
            </label>
            <input
              id="brk-name"
              type="text"
              value={form.accountName}
              onChange={(e) => handleChange('accountName', e.target.value)}
              className={inputClass}
              placeholder="e.g. OANDA Practice"
              required
            />
          </div>

          {/* Row: Broker Type + Account Number */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="brk-type" className={labelClass}>
                Broker Type
              </label>
              <select
                id="brk-type"
                value={form.brokerType}
                onChange={(e) => handleChange('brokerType', e.target.value as BrokerType)}
                className={selectClass}
              >
                {BROKER_TYPES.map((bt) => (
                  <option key={bt} value={bt}>
                    {bt}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="brk-acc" className={labelClass}>
                Account Number
              </label>
              <input
                id="brk-acc"
                type="text"
                value={form.accountNumber}
                onChange={(e) => handleChange('accountNumber', e.target.value)}
                className={inputClass}
                placeholder="e.g. 123-456-789"
                required
              />
            </div>
          </div>

          {/* Row: Environment */}
          <div>
            <label className={labelClass}>Environment</label>
            <div className="flex gap-2">
              {(['practice', 'live'] as const).map((env) => (
                <button
                  key={env}
                  type="button"
                  onClick={() => handleChange('environment', env)}
                  className={cn(
                    'flex-1 py-2 rounded-md text-xs font-medium transition-colors border',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    form.environment === env
                      ? env === 'live'
                        ? 'bg-loss/10 text-loss border-loss/30'
                        : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30'
                      : 'bg-muted text-muted-foreground border-border hover:text-foreground'
                  )}
                  aria-pressed={form.environment === env}
                >
                  {env === 'live' ? 'Live' : 'Practice'}
                </button>
              ))}
            </div>
          </div>

          {/* Separator */}
          <div className="border-t border-border pt-4">
            <div className="flex items-center gap-2 mb-3">
              <Key className="w-3.5 h-3.5 text-muted-foreground" aria-hidden />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                API Credentials
              </span>
            </div>

            {/* API Key */}
            <div className="mb-3">
              <label htmlFor="brk-apikey" className={labelClass}>
                API Key
              </label>
              <input
                id="brk-apikey"
                type="text"
                value={form.apiKey}
                onChange={(e) => handleChange('apiKey', e.target.value)}
                className={inputClass}
                placeholder="Enter your API key"
              />
            </div>

            {/* API Secret */}
            <div className="mb-3">
              <label htmlFor="brk-apisecret" className={labelClass}>
                API Secret
              </label>
              <input
                id="brk-apisecret"
                type="password"
                value={form.apiSecret}
                onChange={(e) => handleChange('apiSecret', e.target.value)}
                className={inputClass}
                placeholder="Enter your API secret"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="brk-password" className={labelClass}>
                Password
              </label>
              <div className="relative">
                <input
                  id="brk-password"
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => handleChange('password', e.target.value)}
                  className={cn(inputClass, 'pr-9')}
                  placeholder="Account password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <X className="w-3.5 h-3.5" aria-hidden />
                  ) : (
                    <Key className="w-3.5 h-3.5" aria-hidden />
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <button
              type="button"
              onClick={onClose}
              className={cn(
                'px-4 py-2 rounded-md text-xs font-medium transition-colors',
                'bg-muted text-muted-foreground hover:text-foreground',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
              )}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!form.accountName.trim() || !form.accountNumber.trim()}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-md text-xs font-semibold transition-colors',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
              )}
            >
              <Plus className="w-3.5 h-3.5" aria-hidden />
              Add Broker
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export function BrokerConnectionsPageClient() {
  const { theme } = useTheme();
  const [brokers, setBrokers] = useState<BrokerAccount[]>(MOCK_BROKERS);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const handleAdd = useCallback(
    (data: BrokerFormData) => {
      const newBroker: BrokerAccount = {
        id: `BRK-${Date.now()}`,
        accountName: data.accountName.trim(),
        brokerType: data.brokerType,
        accountNumber: data.accountNumber.trim(),
        environment: data.environment,
        status: 'disconnected',
        addedAt: new Date().toISOString(),
      };
      setBrokers((prev) => [newBroker, ...prev]);
      showToast(`Broker "${newBroker.accountName}" added successfully`, 'success');
    },
    [showToast]
  );

  const handleTest = useCallback(
    (id: string) => {
      setTestingId(id);
      setTimeout(() => {
        setBrokers((prev) =>
          prev.map((b) => {
            if (b.id !== id) return b;
            const statuses: ConnectionStatus[] = ['connected', 'connected', 'error'];
            return { ...b, status: statuses[Math.floor(Math.random() * statuses.length)] };
          })
        );
        setTestingId(null);
        showToast(`Connection test completed for account ${id}`, 'success');
      }, 1500);
    },
    [showToast]
  );

  const handleToggle = useCallback(
    (id: string) => {
      setBrokers((prev) =>
        prev.map((b) => {
          if (b.id !== id) return b;
          const newStatus: ConnectionStatus =
            b.status === 'connected' ? 'disconnected' : 'connected';
          showToast(
            `Account "${b.accountName}" ${newStatus === 'connected' ? 'connected' : 'disconnected'}`,
            newStatus === 'connected' ? 'success' : 'error'
          );
          return { ...b, status: newStatus };
        })
      );
    },
    [showToast]
  );

  const handleDelete = useCallback(
    (id: string) => {
      const broker = brokers.find((b) => b.id === id);
      setBrokers((prev) => prev.filter((b) => b.id !== id));
      if (broker) {
        showToast(`Broker "${broker.accountName}" removed`, 'error');
      }
    },
    [brokers, showToast]
  );

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Broker Connections</h1>
          <p className="text-sm text-muted-foreground">
            Manage your broker accounts and API connections
          </p>
        </div>
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors',
            'bg-primary text-primary-foreground hover:bg-primary/90',
            'shadow-lg shadow-primary/20',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
        >
          <Plus className="w-4 h-4" aria-hidden />
          Add Broker
        </button>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3">
        {([
          { label: 'Total Accounts', value: brokers.length.toString(), color: 'text-foreground' },
          {
            label: 'Connected',
            value: brokers.filter((b) => b.status === 'connected').length.toString(),
            color: 'text-profit',
          },
          {
            label: 'With Errors',
            value: brokers.filter((b) => b.status === 'error').length.toString(),
            color: 'text-loss',
          },
        ] as const).map(({ label, value, color }) => (
          <div
            key={label}
            className="bg-card border border-border rounded-lg p-3 text-center"
          >
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              {label}
            </div>
            <div className={cn('text-xl font-mono font-bold tabular-nums', color)}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Broker list */}
      <div className="space-y-3">
        {brokers.length === 0 ? (
          <div className="bg-card border border-border rounded-lg p-8 flex flex-col items-center gap-3 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
              <Plug className="w-6 h-6 text-muted-foreground" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">No broker connections</p>
              <p className="text-xs text-muted-foreground mt-1">
                Add a broker account to start trading
              </p>
            </div>
          </div>
        ) : (
          brokers.map((account) => (
            <BrokerCard
              key={account.id}
              account={account}
              onTest={handleTest}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>

      {/* Testing spinner overlay */}
      {testingId && (
        <div className="fixed bottom-6 right-6 z-40 flex items-center gap-2 bg-card border border-border rounded-lg px-4 py-3 shadow-xl">
          <RefreshCw className="w-4 h-4 text-primary animate-spin" aria-hidden />
          <span className="text-xs text-muted-foreground">Testing connection...</span>
        </div>
      )}

      {/* Demo mode note */}
      <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-yellow-500/10 flex items-center justify-center flex-shrink-0">
            <TestTubes className="w-4 h-4 text-yellow-400" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">
              Demo Mode — Broker API Not Connected
            </p>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              The broker connection backend is still in development. Account data shown here is
              mock data for demonstration purposes. Real API calls will be enabled once the
              backend broker integration is complete.
            </p>
          </div>
        </div>
      </div>

      {/* Inline toast notification */}
      {toast && (
        <div
          className={cn(
            'fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-lg shadow-xl border text-sm font-medium transition-all',
            toast.type === 'success'
              ? 'bg-profit/10 border-profit/20 text-profit'
              : 'bg-loss/10 border-loss/20 text-loss'
          )}
        >
          {toast.message}
        </div>
      )}

      {/* Add Broker Modal */}
      <AddBrokerModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onAdd={handleAdd}
      />
    </div>
  );
}
