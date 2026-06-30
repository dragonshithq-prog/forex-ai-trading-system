import type { Metadata } from 'next';
import { ResetConfirmClient } from './ResetConfirmClient';

export const metadata: Metadata = {
  title: 'Set New Password | Forex AI',
  description: 'Reset your password with your reset token',
};

export default function ResetConfirmPage() {
  return <ResetConfirmClient />;
}
