'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Bot, Loader2, Mail, ArrowLeft, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const requestSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
});

type ResetFormValues = z.infer<typeof requestSchema>;

export function ResetRequestClient() {
  const [sent, setSent] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetFormValues>({
    resolver: zodResolver(requestSchema),
  });

  const onSubmit = async (data: ResetFormValues) => {
    try {
      await api.auth.requestPasswordReset(data.email);
      setSent(true);
    } catch {
      toast.error('Failed to send reset request. Please try again.');
    }
  };

  const inputClass = cn(
    'w-full bg-muted/50 border border-border rounded-lg px-4 py-3 text-sm text-foreground',
    'placeholder:text-muted-foreground/50',
    'focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring',
    'transition-colors'
  );

  if (sent) {
    return (
      <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="w-full max-w-md">
          <div className="bg-card border border-border rounded-2xl p-8 shadow-2xl text-center">
            <CheckCircle className="w-12 h-12 text-profit mx-auto mb-4" aria-hidden />
            <h2 className="text-xl font-semibold text-foreground mb-2">Check Your Email</h2>
            <p className="text-sm text-muted-foreground mb-6">
              If an account with that email exists, a reset token has been generated.
              <br />Use it on the reset confirmation page.
            </p>
            <Link href="/reset-password/confirm"
              className="inline-block w-full py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors text-center mb-3">
              Enter Reset Token
            </Link>
            <Link href="/login" className="block text-sm text-primary hover:underline">
              Back to Sign In
            </Link>
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
          <h1 className="text-2xl font-bold text-foreground">Reset Password</h1>
          <p className="text-sm text-muted-foreground mt-1">We'll send you a reset token</p>
        </div>

        <div className="bg-card border border-border rounded-2xl p-6 shadow-2xl">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-foreground mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
                <input id="email" type="email" autoComplete="email" placeholder="you@example.com"
                  {...register('email')} className={cn(inputClass, 'pl-10')}
                  aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />
              </div>
              {errors.email && <p id="email-error" role="alert" className="text-xs text-loss mt-1.5">{errors.email.message}</p>}
            </div>

            <button type="submit" disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-colors">
              {isSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" aria-hidden />Sending...</> : 'Send Reset Token'}
            </button>
          </form>

          <Link href="/login" className="flex items-center justify-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mt-4">
            <ArrowLeft className="w-3.5 h-3.5" aria-hidden /> Back to Sign In
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
