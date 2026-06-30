'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Bot, Eye, EyeOff, Loader2, Lock, User, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/store/authStore';
import { toast } from 'sonner';

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
  mfa_token: z.string().optional(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

const DEMO_CREDENTIALS = {
  username: 'demo',
  password: 'demo',
};

export function LoginPageClient() {
  const router = useRouter();
  const { setUser, setTokens } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [requiresMfa, setRequiresMfa] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    try {
      const response = await api.auth.login({
        username: data.username,
        password: data.password,
        mfa_token: data.mfa_token,
      });

      setUser(response.user);
      setTokens(response.access_token, response.refresh_token);
      toast.success(`Welcome back, ${response.user.username}!`);
      router.push('/dashboard');
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 428) {
        setRequiresMfa(true);
        toast.info('Please enter your MFA code to continue.');
      } else if (status === 401) {
        toast.error('Invalid username or password. Please try again.');
      } else {
        toast.error('Unable to connect. Using demo mode — click "Demo Login".');
      }
    }
  };

  const handleDemoLogin = () => {
    setValue('username', DEMO_CREDENTIALS.username);
    setValue('password', DEMO_CREDENTIALS.password);
    handleSubmit(onSubmit)();
  };

  const inputClass = cn(
    'w-full bg-muted/50 border border-border rounded-lg px-4 py-3 text-sm text-foreground',
    'placeholder:text-muted-foreground/50',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring',
    'transition-colors'
  );
  const errorClass = 'text-xs text-loss mt-1.5 flex items-center gap-1';

  return (
    <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4">
            <Bot className="w-7 h-7 text-primary" aria-hidden />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Forex AI Platform</h1>
          <p className="text-sm text-muted-foreground mt-1">Institutional AI trading system</p>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-2xl">
          <h2 className="text-lg font-semibold text-foreground mb-1">Sign in</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Enter your credentials to access the trading terminal
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {/* Username */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-foreground mb-1.5">
                Username
              </label>
              <div className="relative">
                <User
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                  aria-hidden
                />
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  placeholder="Enter your username"
                  {...register('username')}
                  className={cn(inputClass, 'pl-10')}
                  aria-invalid={!!errors.username}
                  aria-describedby={errors.username ? 'username-error' : undefined}
                />
              </div>
              {errors.username && (
                <p id="username-error" role="alert" className={errorClass}>
                  {errors.username.message}
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                  aria-hidden
                />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  {...register('password')}
                  className={cn(inputClass, 'pl-10 pr-12')}
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'password-error' : undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" aria-hidden /> : <Eye className="w-4 h-4" aria-hidden />}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" role="alert" className={errorClass}>
                  {errors.password.message}
                </p>
              )}
              <div className="flex justify-end mt-1">
                <Link href="/reset-password/request" className="text-xs text-muted-foreground hover:text-primary transition-colors">
                  Forgot password?
                </Link>
              </div>
            </div>

            {/* MFA (shown conditionally) */}
            {requiresMfa && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
              >
                <label htmlFor="mfa" className="block text-sm font-medium text-foreground mb-1.5">
                  MFA Code
                </label>
                <div className="relative">
                  <ShieldCheck
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground"
                    aria-hidden
                  />
                  <input
                    id="mfa"
                    type="text"
                    maxLength={6}
                    inputMode="numeric"
                    pattern="[0-9]*"
                    autoComplete="one-time-code"
                    placeholder="6-digit code"
                    {...register('mfa_token')}
                    className={cn(inputClass, 'pl-10 tracking-[0.4em] font-mono text-center')}
                  />
                </div>
              </motion.div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring mt-2"
            >
              {isSubmitting ? (
                <><Loader2 className="w-4 h-4 animate-spin" aria-hidden />Signing in...</>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="relative my-4">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-card px-2 text-xs text-muted-foreground">or</span>
            </div>
          </div>

          {/* Demo login */}
          <button
            onClick={handleDemoLogin}
            disabled={isSubmitting}
            className="w-full py-3 rounded-lg border border-border bg-muted/30 text-sm font-medium text-foreground hover:bg-muted/60 disabled:opacity-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Try Demo Mode
          </button>

          <p className="text-center text-xs text-muted-foreground mt-4">
            Demo uses mock data — no real trades are executed
          </p>

          <p className="text-center text-sm text-muted-foreground mt-4">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="text-primary hover:underline font-medium">
              Create one
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-muted-foreground mt-6">
          Institutional AI Forex Trading System v0.1
        </p>
      </motion.div>
    </div>
  );
}
