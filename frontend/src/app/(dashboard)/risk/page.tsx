import type { Metadata } from 'next';
import { RiskPageClient } from './RiskPageClient';

export const metadata: Metadata = { title: 'Risk Management' };

export default function RiskPage() {
  return <RiskPageClient />;
}
