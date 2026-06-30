'use client';
import { TradeJournal } from '@/components/trading/TradeJournal';
import { MOCK_JOURNAL_ENTRIES } from '@/lib/mockData';

export function JournalPageClient() {
  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Trade Journal</h1>
        <p className="text-sm text-muted-foreground">Review and annotate your trading history</p>
      </div>
      <div className="max-w-3xl">
        <TradeJournal entries={MOCK_JOURNAL_ENTRIES} />
      </div>
    </div>
  );
}
