'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Bot, Loader2, Lock, Eye, EyeOff, KeyRound, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const resetSchema = z.object({
  token: z.string().min(1, 'Reset token is required'),
  new_password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number'),
  confirm_password: z.string(),
}).refine((data) => data.new_password === data.confirm_password, {
  message: 'Passwords do not match',
  path: ['confirm_password'],
});

type ResetFormValues = z.infer<typeof resetSchema>;

export function ResetConfirmClient() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetFormValues>({
    resolver: zodResolver(resetSchema),
  });

  const onSubmit = async (data: ResetFormValues) => {
    try {
      await api.auth.confirmPasswordReset(data.token, data.new_password);
      setSuccess(true);
      toast.success('Password reset successfully!');
      setTimeout(() => router.push('/login'), 2000);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to reset password. The token may be invalid or expired.');
    }
  };

  const inputClass = cn(
    'w-full bg-muted/50 border border-border rounded-lg px-4 py-3 text-sm text-foreground',
    'placeholder:text-muted-foreground/50',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring',
    'transition-colors'
  );

  if (success) {
    return (
      <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="w-full max-w-md">
          <div className="bg-card border border-border rounded-2xl p-8 shadow-2xl text-center">
            <CheckCircle className="w-12 h-12 text-profit mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">Password Reset!</h2>
            <p className="text-sm text-muted-foreground mb-6">Redirecting you to sign in...</p>
          </div>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4">
            <Bot className="w-7 h-7 text-primary" aria-hidden />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Set New Password</h1>
          <p className="text-sm text-muted-foreground mt-1">Enter your reset token and new password</p>
        </div>

        <div className="bg-card border border-border rounded-2xl p-6 shadow-2xl">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="token" className="block text-sm font-medium text-foreground mb-1.5">
                Reset Token
              </label>
              <div className="relative">
                <KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="token" type="text" placeholder="Paste your reset token"
                  {...register('token')} className={cn(inputClass, 'pl-10 font-mono text-sm')}
                  aria-invalid={!!errors.token} />
              </div>
              {errors.token && <p role="alert" className="text-xs text-loss mt-1.5">{errors.token.message}</p>}
            </div>

            <div>
              <label htmlFor="new_password" className="block text-sm font-medium text-foreground mb-1.5">
                New Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="new_password" type={showPassword ? 'text' : 'password'} autoComplete="new-password"
                  placeholder="Min. 8 characters with uppercase & number"
                  {...register('new_password')} className={cn(inputClass, 'pl-10 pr-12')}
                  aria-invalid={!!errors.new_password} />
                <button type="button" onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}>
                  {showPassword ? <EyeOff className="w-4 h-4" aria-hidden /> : <Eye className="w-4 h-4" aria-hidden />}
                </button>
              </div>
              {errors.new_password && <p role="alert" className="text-xs text-loss mt-1.5">{errors.new_password.message}</p>}
            </div>

            <div>
              <label htmlFor="confirm_password" className="block text-sm font-medium text-foreground mb-1.5">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="confirm_password" type="password" autoComplete="new-password" placeholder="Repeat your password"
                  {...register('confirm_password')} className={cn(inputClass, 'pl-10')}
                  aria-invalid={!!errors.confirm_password} />
              </div>
              {errors.confirm_password && <p role="alert" className="text-xs text-loss mt-1.5">{errors.confirm_password.message}</p>}
            </div>

            <button type="submit" disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors mt-2">
              {isSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" aria-hidden />Resetting...</> : 'Reset Password'}
            </button>
          </form>

          <Link href="/login" className="block text-center text-sm text-muted-foreground hover:text-foreground transition-colors mt-4">
            Back to Sign In
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
