import type { Metadata } from 'next';
import { LoginPageClient } from './LoginPageClient';

export const metadata: Metadata = {
  title: 'Sign In | Forex AI',
  description: 'Sign in to your Forex AI trading account',
};

export default function LoginPage() {
  return <LoginPageClient />;
}
