import type { Metadata } from 'next';
import { AdminPageClient } from './AdminPageClient';

export const metadata: Metadata = {
  title: 'Admin Panel | Forex AI',
  description: 'User management and administrative controls',
};

export default function AdminPage() {
  return <AdminPageClient />;
}
