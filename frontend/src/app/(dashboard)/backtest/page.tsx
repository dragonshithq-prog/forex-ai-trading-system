import type { Metadata } from 'next';
import { BacktestPageClient } from './BacktestPageClient';

export const metadata: Metadata = { title: 'Backtesting' };

export default function BacktestPage() {
  return <BacktestPageClient />;
}
