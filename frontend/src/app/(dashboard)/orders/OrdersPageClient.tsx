'use client';
import { useState } from 'react';
import { useOrders } from '@/lib/hooks/useOrders';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { formatDateTime, formatCurrency } from '@/lib/utils/formatters';
import { getSideBgColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';

const STATUS_VARIANT: Record<string, 'success' | 'danger' | 'warning' | 'info' | 'neutral' | 'default'> = {
  filled: 'success',
  cancelled: 'neutral',
  rejected: 'danger',
  pending: 'warning',
  open: 'info',
  partial: 'warning',
};

export function OrdersPageClient() {
  const [page, setPage] = useState(1);
  const { orders, total, pages, isLoading } = useOrders({ page, page_size: 20 });

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Order History</h1>
        <p className="text-sm text-muted-foreground">
          {total} total orders
        </p>
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner label="Loading orders..." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-border">
                  {['Time', 'Symbol', 'Side', 'Type', 'Qty', 'Price', 'Filled', 'Commission', 'Status'].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-xs text-muted-foreground font-medium uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-center py-10 text-sm text-muted-foreground">
                      No orders found
                    </td>
                  </tr>
                ) : (
                  orders.map((order) => (
                    <tr
                      key={order.id}
                      className="border-b border-border/50 hover:bg-muted/20 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {formatDateTime(order.created_at)}
                      </td>
                      <td className="px-4 py-3 font-mono font-medium text-foreground">
                        {order.symbol}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={order.side.toUpperCase() === 'BUY' ? 'buy' : 'sell'}
                          size="sm"
                        >
                          {order.side.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground capitalize">
                        {order.order_type}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums">
                        {order.quantity}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums text-foreground">
                        {order.price ? order.price.toFixed(5) : 'Market'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums">
                        {order.filled_price ? order.filled_price.toFixed(5) : '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums text-muted-foreground">
                        {formatCurrency(-order.commission)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={STATUS_VARIANT[order.status] ?? 'default'}
                          size="sm"
                        >
                          {order.status}
                        </Badge>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <p className="text-xs text-muted-foreground">
              Page {page} of {pages}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-xs rounded-md bg-muted text-foreground disabled:opacity-50 hover:bg-muted/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="px-3 py-1.5 text-xs rounded-md bg-muted text-foreground disabled:opacity-50 hover:bg-muted/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
