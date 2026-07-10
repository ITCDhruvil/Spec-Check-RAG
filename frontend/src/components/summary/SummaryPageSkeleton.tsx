"use client";

import Link from "next/link";

import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";

/** Static shell shown during SSR and until client mount (avoids hydration mismatch). */
export function SummaryPageSkeleton() {
  const header = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <Link href="/" className="text-xs text-ink-muted hover:text-ink">
          ← Dashboard
        </Link>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          Specification briefing
        </h2>
        <p className="mt-1 text-sm text-ink-muted">Your document</p>
      </div>
    </div>
  );

  const briefing = (
    <div className="space-y-6">
      <div className="rounded-lg border border-surface-border bg-surface p-6">
        <div className="flex items-center gap-3">
          <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-surface-muted" />
          <div className="h-4 w-48 animate-pulse rounded bg-surface-muted" />
        </div>
        <div className="mt-5 h-1.5 w-full animate-pulse rounded-full bg-surface-muted" />
      </div>
      <p className="sr-only">Loading status…</p>
    </div>
  );

  const preview = (
    <div className="flex h-full min-h-[320px] flex-col">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Document preview</h3>
          <p className="mt-0.5 truncate text-xs text-ink-muted">Loading…</p>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-surface-border bg-surface">
        <p className="text-sm text-ink-muted">Loading PDF preview…</p>
      </div>
    </div>
  );

  return (
    <SplitPanelLayout header={header} left={briefing} right={preview} />
  );
}
