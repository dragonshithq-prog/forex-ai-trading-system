'use client';
import { ThemeProvider as NextThemesProvider } from 'next-themes';
import type { ThemeProviderProps } from 'next-themes/dist/types';
import { useEffect } from 'react';

export const THEMES = [
  { id: 'dark', name: 'Dark', icon: '🌙', description: 'Classic dark trading terminal' },
  { id: 'light', name: 'Light', icon: '☀️', description: 'Clean light interface' },
  { id: 'midnight', name: 'Midnight', icon: '🌃', description: 'Deep blue ambient theme' },
  { id: 'emerald', name: 'Emerald', icon: '💎', description: 'Green-focused premium theme' },
  { id: 'matrix', name: 'Matrix', icon: '💚', description: 'Classic green-on-black terminal' },
] as const;

export type ThemeId = (typeof THEMES)[number]['id'];

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  useEffect(() => {
    const handler = () => {
      const current = document.documentElement.className;
      const next = current.includes('dark') ? 'light' : 'dark';
      document.documentElement.className = next;
    };
    window.addEventListener('toggle-theme', handler);
    return () => window.removeEventListener('toggle-theme', handler);
  }, []);

  return <NextThemesProvider themes={['dark', 'light', 'midnight', 'emerald', 'matrix']} {...props}>{children}</NextThemesProvider>;
}
