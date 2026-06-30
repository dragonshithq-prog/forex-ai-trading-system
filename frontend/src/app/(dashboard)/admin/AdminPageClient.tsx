'use client';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, Search, Users, RotateCcw, Check, X, Loader2,
  Lock, UserCheck, UserX, ChevronDown, MoreHorizontal,
  KeyRound, AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { api } from '@/lib/api';
import { useAuthStore } from '@/lib/store/authStore';
import { toast } from 'sonner';
import type { User } from '@/types/api';

const passwordSchema = z.object({
  new_password: z.string().min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain uppercase')
    .regex(/[a-z]/, 'Must contain lowercase')
    .regex(/[0-9]/, 'Must contain a number'),
});

export function AdminPageClient() {
  const router = useRouter();
  const { user: currentUser } = useAuthStore();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [passwordModal, setPasswordModal] = useState<User | null>(null);
  const [roleMenu, setRoleMenu] = useState<string | null>(null);

  const isSuperAdmin = currentUser?.role === 'superadmin';

  const fetchUsers = useCallback(async (q = '') => {
    setLoading(true);
    try {
      const res = q
        ? await api.admin.searchUsers(q)
        : await api.admin.listUsers();
      setUsers(res.users);
      setTotal(res.total);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentUser && !['admin', 'superadmin'].includes(currentUser.role)) {
      router.push('/dashboard');
      return;
    }
    fetchUsers();
  }, [currentUser, router, fetchUsers]);

  const handleToggleActive = async (userId: string) => {
    try {
      const updated = await api.admin.toggleActive(userId);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      toast.success(`User ${updated.is_active ? 'activated' : 'deactivated'}`);
    } catch {
      toast.error('Failed to toggle user status');
    }
  };

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      const updated = await api.admin.updateRole(userId, role);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      toast.success(`Role updated to ${role}`);
      setRoleMenu(null);
    } catch {
      toast.error('Failed to update role');
    }
  };

  const handlePasswordReset = async (userId: string) => {
    if (!passwordModal) return;
    const pw = (document.getElementById('admin-reset-password') as HTMLInputElement)?.value;
    if (!pw || pw.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    try {
      await api.admin.resetPassword(userId, pw);
      toast.success('Password reset successfully');
      setPasswordModal(null);
    } catch {
      toast.error('Failed to reset password');
    }
  };

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      superadmin: 'bg-purple-500/10 text-purple-500 border-purple-500/30',
      admin: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
      trader: 'bg-green-500/10 text-green-500 border-green-500/30',
      viewer: 'bg-muted text-muted-foreground border-border',
    };
    return (
      <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium border', colors[role] || colors.viewer)}>
        {role}
      </span>
    );
  };

  const inputClass = 'w-full bg-muted/50 border border-border rounded-lg px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring transition-colors';

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Shield className="w-6 h-6 text-primary" /> Admin Panel
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage users, roles, and security settings
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="w-4 h-4" />
          <span>{total} user{total !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden />
        <input
          type="text"
          placeholder="Search by username or email..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            fetchUsers(e.target.value);
          }}
          className={cn(inputClass, 'pl-10')}
        />
      </div>

      {/* Users table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">User</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">Email</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">Role</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">Last Login</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                    No users found
                  </td>
                </tr>
              ) : (
                <AnimatePresence>
                  {users.map((u, i) => (
                    <motion.tr
                      key={u.id}
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.02 }}
                      className="border-b border-border/50 hover:bg-muted/20 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-xs font-semibold text-primary">
                            {u.username.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="font-medium text-foreground">{u.username}</p>
                            {u.full_name && <p className="text-xs text-muted-foreground">{u.full_name}</p>}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                      <td className="px-4 py-3 relative">
                        <button
                          onClick={() => setRoleMenu(roleMenu === u.id ? null : u.id)}
                          className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
                          disabled={!isSuperAdmin && u.role === 'superadmin'}
                        >
                          {roleBadge(u.role)}
                          {(isSuperAdmin || u.role !== 'superadmin') && <ChevronDown className="w-3 h-3 text-muted-foreground" />}
                        </button>
                        {roleMenu === u.id && (
                          <div className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-xl z-10 py-1 min-w-[140px]">
                            {['superadmin', 'admin', 'trader', 'viewer'].map((role) => (
                              <button
                                key={role}
                                onClick={() => handleRoleChange(u.id, role)}
                                className={cn(
                                  'w-full text-left px-3 py-1.5 text-sm hover:bg-muted/50 transition-colors',
                                  u.role === role ? 'text-primary font-medium' : 'text-foreground'
                                )}
                                disabled={!isSuperAdmin && role === 'superadmin'}
                              >
                                {role}
                              </button>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          'flex items-center gap-1.5 text-xs font-medium',
                          u.is_active ? 'text-profit' : 'text-loss'
                        )}>
                          {u.is_active ? <UserCheck className="w-3.5 h-3.5" /> : <UserX className="w-3.5 h-3.5" />}
                          {u.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {u.last_login ? new Date(u.last_login).toLocaleDateString() : 'Never'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleToggleActive(u.id)}
                            disabled={u.id === currentUser?.id}
                            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                            title={u.is_active ? 'Deactivate' : 'Activate'}
                          >
                            {u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                          </button>
                          <button
                            onClick={() => setPasswordModal(u)}
                            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                            title="Reset Password"
                          >
                            <KeyRound className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Password Reset Modal */}
      <AnimatePresence>
        {passwordModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={() => setPasswordModal(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-card border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-amber-500" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground">Reset Password</h3>
                  <p className="text-sm text-muted-foreground">
                    New password for <strong>{passwordModal.username}</strong>
                  </p>
                </div>
              </div>
              <input
                id="admin-reset-password"
                type="password"
                placeholder="New password (min. 8 chars, upper + number)"
                className={cn(inputClass, 'mb-4')}
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handlePasswordReset(passwordModal.id)}
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setPasswordModal(null)}
                  className="px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-muted/50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handlePasswordReset(passwordModal.id)}
                  className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors"
                >
                  Reset Password
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
