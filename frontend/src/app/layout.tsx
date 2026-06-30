import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import { Toaster } from 'sonner';
import { CommandPalette } from '@/components/common/CommandPalette';
import { AuthInit } from '@/components/common/AuthInit';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: {
    default: 'Forex AI Trading Platform',
    template: '%s | Forex AI',
  },
  description: 'Institutional-grade AI Forex trading dashboard',
  robots: 'noindex, nofollow',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0a0a0a',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-background antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <AuthInit />
          {children}
          <CommandPalette />
          <Toaster
            position="top-right"
            offset={80}
            toastOptions={{
              style: {
                background: 'hsl(0 0% 9%)',
                border: '1px solid hsl(0 0% 13%)',
                color: 'hsl(0 0% 95%)',
              },
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
