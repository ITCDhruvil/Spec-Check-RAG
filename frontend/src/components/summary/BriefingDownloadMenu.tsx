"use client";

import { useState } from "react";

import { downloadBriefingPdf } from "@/lib/api/intelligence";

export function BriefingDownloadMenu({
  documentId,
  filename,
}: {
  documentId: string;
  filename: string;
}) {
  const [loading, setLoading] = useState<"full" | "executive" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload(variant: "full" | "executive") {
    setError(null);
    setLoading(variant);
    try {
      await downloadBriefingPdf(documentId, filename, variant);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => handleDownload("full")}
          disabled={loading !== null}
          className="rounded-md border border-surface-border bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-surface-muted disabled:opacity-50"
        >
          {loading === "full" ? "Preparing PDF…" : "Download full report (PDF)"}
        </button>
        <button
          type="button"
          onClick={() => handleDownload("executive")}
          disabled={loading !== null}
          className="rounded-md border border-surface-border px-4 py-2 text-sm font-medium text-ink-muted hover:bg-surface-muted hover:text-ink disabled:opacity-50"
        >
          {loading === "executive"
            ? "Preparing PDF…"
            : "Executive summary (PDF)"}
        </button>
      </div>
      {error && (
        <p className="max-w-xs text-right text-xs text-red-600">{error}</p>
      )}
    </div>
  );
}
