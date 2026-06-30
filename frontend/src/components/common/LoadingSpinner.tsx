import { cn } from '@/lib/utils/cn';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  label?: string;
}

const sizeMap = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' };
const borderMap = { sm: 'border-2', md: 'border-2', lg: 'border-[3px]' };

export function LoadingSpinner({
  size = 'md',
  className,
  label = 'Loading...',
}: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn('flex items-center justify-center', className)}
    >
      <div
        className={cn(
          'rounded-full border-transparent border-t-primary animate-spin',
          'border-muted',
          sizeMap[size],
          borderMap[size]
        )}
        style={{ borderTopColor: 'hsl(var(--primary))' }}
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function PageLoader() {
  return (
    <div className="flex-1 flex items-center justify-center min-h-[400px]">
      <div className="flex flex-col items-center gap-3">
        <LoadingSpinner size="lg" />
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    </div>
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn('bg-card border border-border rounded-lg p-4 animate-pulse', className)}
      aria-hidden
    >
      <div className="h-3 bg-muted rounded w-1/3 mb-4" />
      <div className="h-7 bg-muted rounded w-1/2 mb-2" />
      <div className="h-3 bg-muted rounded w-1/4" />
    </div>
  );
}
