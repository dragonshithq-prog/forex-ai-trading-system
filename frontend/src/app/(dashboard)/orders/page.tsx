import type { Metadata } from 'next';
import { OrdersPageClient } from './OrdersPageClient';

export const metadata: Metadata = { title: 'Orders' };

export default function OrdersPage() {
  return <OrdersPageClient />;
}
