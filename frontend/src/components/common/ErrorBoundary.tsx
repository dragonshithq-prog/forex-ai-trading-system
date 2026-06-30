'use client';
import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center p-6 text-center rounded-lg bg-card border border-border gap-3"
        >
          <div className="w-10 h-10 rounded-full bg-loss/10 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-loss" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Something went wrong</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-xs">
              {this.state.error?.message ?? 'An unexpected error occurred in this component.'}
            </p>
          </div>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
          >
            <RefreshCw className="w-3 h-3" aria-hidden />
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
