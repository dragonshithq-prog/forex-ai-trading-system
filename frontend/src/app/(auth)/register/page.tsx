import type { Metadata } from 'next';
import { RegisterPageClient } from './RegisterPageClient';

export const metadata: Metadata = {
  title: 'Create Account | Forex AI',
  description: 'Create your Forex AI trading account',
};

export default function RegisterPage() {
  return <RegisterPageClient />;
}
