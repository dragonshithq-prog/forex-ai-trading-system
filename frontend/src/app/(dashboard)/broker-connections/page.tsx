import type { Metadata } from 'next';
import { BrokerConnectionsPageClient } from './BrokerConnectionsPageClient';

export const metadata: Metadata = { title: 'Broker Connections' };

export default function BrokerConnectionsPage() {
  return <BrokerConnectionsPageClient />;
}
