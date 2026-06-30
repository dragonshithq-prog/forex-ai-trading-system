import type { Metadata } from 'next';
import { ResetRequestClient } from './ResetRequestClient';

export const metadata: Metadata = {
  title: 'Reset Password | Forex AI',
  description: 'Request a password reset link',
};

export default function ResetRequestPage() {
  return <ResetRequestClient />;
}
