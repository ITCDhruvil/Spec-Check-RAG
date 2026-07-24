"use client";

import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";
import { SpokesLoader } from "@/components/ui/Spokes";
import { usePageHeader } from "@/lib/pageHeaderContext";

/** Static shell shown during SSR and until client mount (avoids hydration mismatch). */
export function SummaryPageSkeleton() {
  // Header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "Specification briefing",
  });

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
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
        <p className="min-w-0 truncate text-xs font-medium text-ink">Loading…</p>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-surface-border bg-surface">
        <SpokesLoader label="Loading PDF preview…" className="py-0" />
      </div>
    </div>
  );

  return <SplitPanelLayout left={briefing} right={preview} />;
}
