import type { DocumentListItem } from "@/lib/types/document";
import { ACTIVE_STAGES } from "@/lib/types/document";

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-ink">
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

function formatTotalSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB total`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB total`;
}

export function computeDashboardStats(documents: DocumentListItem[]) {
  let completed = 0;
  let processing = 0;
  let failed = 0;
  let totalBytes = 0;
  const tenders = new Set<string>();

  for (const doc of documents) {
    totalBytes += doc.size_bytes;
    if (doc.tender_reference) tenders.add(doc.tender_reference);
    if (doc.status === "completed") completed += 1;
    else if (doc.status === "failed") failed += 1;
    else if (
      doc.status === "queued" ||
      ACTIVE_STAGES.includes(doc.status)
    ) {
      processing += 1;
    }
  }

  return {
    total: documents.length,
    completed,
    processing,
    failed,
    tenderCount: tenders.size,
    totalBytes,
  };
}

export function DashboardStats({ documents }: { documents: DocumentListItem[] }) {
  const stats = computeDashboardStats(documents);

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Documents" value={stats.total} hint="Uploaded tenders" />
      <StatCard
        label="Ready"
        value={stats.completed}
        hint="Summary available"
      />
      <StatCard
        label="In progress"
        value={stats.processing}
        hint={stats.processing > 0 ? "Auto-refreshes every 5s" : "None active"}
      />
      <StatCard
        label="Failed"
        value={stats.failed}
        hint={
          stats.tenderCount > 0
            ? `${stats.tenderCount} tender ref · ${formatTotalSize(stats.totalBytes)}`
            : formatTotalSize(stats.totalBytes)
        }
      />
    </div>
  );
}
