import type { Metadata } from 'next';
import { PositionsPageClient } from './PositionsPageClient';

export const metadata: Metadata = { title: 'Positions' };

export default function PositionsPage() {
  return <PositionsPageClient />;
}
