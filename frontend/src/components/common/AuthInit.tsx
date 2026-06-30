'use client';
import { useEffect } from 'react';
import { useAuthStore } from '@/lib/store/authStore';
import { api } from '@/lib/api';

export function AuthInit() {
  const setUser = useAuthStore((s) => s.setUser);
  const setTokens = useAuthStore((s) => s.setTokens);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) {
      api.auth.login({ username: 'demo', password: 'demo' }).then((res) => {
        setUser(res.user);
        setTokens(res.access_token, res.refresh_token);
      }).catch(() => {
        // Silently fail — demo mode fallback will handle it
      });
    }
  }, [isAuthenticated, setUser, setTokens]);

  return null;
}
