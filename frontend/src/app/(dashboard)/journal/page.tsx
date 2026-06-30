import type { Metadata } from 'next';
import { JournalPageClient } from './JournalPageClient';

export const metadata: Metadata = { title: 'Trade Journal' };

export default function JournalPage() {
  return <JournalPageClient />;
}
