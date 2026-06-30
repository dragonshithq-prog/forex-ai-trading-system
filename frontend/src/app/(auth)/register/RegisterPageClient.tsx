'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Bot, Eye, EyeOff, Loader2, Mail, User, Lock, UserCircle } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/store/authStore';
import { toast } from 'sonner';

const registerSchema = z.object({
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(50, 'Username must be under 50 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Username can only contain letters, numbers, hyphens, and underscores'),
  email: z.string().email('Please enter a valid email address'),
  full_name: z.string().max(255).optional(),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number'),
  confirm_password: z.string(),
}).refine((data) => data.password === data.confirm_password, {
  message: 'Passwords do not match',
  path: ['confirm_password'],
});

type RegisterFormValues = z.infer<typeof registerSchema>;

export function RegisterPageClient() {
  const router = useRouter();
  const { setUser, setTokens } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterFormValues) => {
    try {
      const response = await api.auth.register({
        username: data.username,
        email: data.email,
        password: data.password,
        full_name: data.full_name || undefined,
      });
      setUser(response.user);
      setTokens(response.access_token, response.refresh_token);
      toast.success('Account created successfully! Welcome aboard.');
      router.push('/dashboard');
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (status === 409) {
        toast.error(detail || 'Username or email already registered');
      } else {
        toast.error('Registration failed. Please try again.');
      }
    }
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
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4">
            <Bot className="w-7 h-7 text-primary" aria-hidden />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Create Account</h1>
          <p className="text-sm text-muted-foreground mt-1">Join the institutional AI trading platform</p>
        </div>

        <div className="bg-card border border-border rounded-2xl p-6 shadow-2xl">
          <h2 className="text-lg font-semibold text-foreground mb-1">Sign up</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Fill in your details to get started
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-foreground mb-1.5">
                Username
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="username" type="text" autoComplete="username" placeholder="Choose a username"
                  {...register('username')} className={cn(inputClass, 'pl-10')}
                  aria-invalid={!!errors.username} aria-describedby={errors.username ? 'username-error' : undefined} />
              </div>
              {errors.username && <p id="username-error" role="alert" className={errorClass}>{errors.username.message}</p>}
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-foreground mb-1.5">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="email" type="email" autoComplete="email" placeholder="you@example.com"
                  {...register('email')} className={cn(inputClass, 'pl-10')}
                  aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />
              </div>
              {errors.email && <p id="email-error" role="alert" className={errorClass}>{errors.email.message}</p>}
            </div>

            <div>
              <label htmlFor="full_name" className="block text-sm font-medium text-foreground mb-1.5">
                Full Name <span className="text-muted-foreground">(optional)</span>
              </label>
              <div className="relative">
                <UserCircle className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="full_name" type="text" autoComplete="name" placeholder="John Doe"
                  {...register('full_name')} className={cn(inputClass, 'pl-10')} />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-foreground mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="password" type={showPassword ? 'text' : 'password'} autoComplete="new-password"
                  placeholder="Min. 8 characters with uppercase & number"
                  {...register('password')} className={cn(inputClass, 'pl-10 pr-12')}
                  aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : undefined} />
                <button type="button" onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}>
                  {showPassword ? <EyeOff className="w-4 h-4" aria-hidden /> : <Eye className="w-4 h-4" aria-hidden />}
                </button>
              </div>
              {errors.password && <p id="password-error" role="alert" className={errorClass}>{errors.password.message}</p>}
            </div>

            <div>
              <label htmlFor="confirm_password" className="block text-sm font-medium text-foreground mb-1.5">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="confirm_password" type={showConfirm ? 'text' : 'password'} autoComplete="new-password"
                  placeholder="Repeat your password"
                  {...register('confirm_password')} className={cn(inputClass, 'pl-10 pr-12')}
                  aria-invalid={!!errors.confirm_password} />
                <button type="button" onClick={() => setShowConfirm((s) => !s)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-label={showConfirm ? 'Hide password' : 'Show password'}>
                  {showConfirm ? <EyeOff className="w-4 h-4" aria-hidden /> : <Eye className="w-4 h-4" aria-hidden />}
                </button>
              </div>
              {errors.confirm_password && <p role="alert" className={errorClass}>{errors.confirm_password.message}</p>}
            </div>

            <button type="submit" disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring mt-2">
              {isSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" aria-hidden />Creating account...</> : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-6">
            Already have an account?{' '}
            <Link href="/login" className="text-primary hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          Institutional AI Forex Trading System v0.1
        </p>
      </motion.div>
    </div>
  );
}
