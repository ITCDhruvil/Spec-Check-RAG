"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DocumentActionsMenu } from "@/components/documents/DocumentActionsMenu";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Pagination, paginateSlice } from "@/components/ui/Pagination";
import type { DocumentListItem } from "@/lib/types/document";
import { ACTIVE_STAGES } from "@/lib/types/document";

const PAGE_SIZE = 10;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

type StatusFilter = "all" | "ready" | "processing" | "failed";

const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "ready", label: "Ready" },
  { id: "processing", label: "In progress" },
  { id: "failed", label: "Failed" },
];

function matchesFilter(doc: DocumentListItem, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "ready") return doc.status === "completed";
  if (filter === "failed") return doc.status === "failed";
  return (
    doc.status === "queued" || ACTIVE_STAGES.includes(doc.status)
  );
}

export function DocumentTable({
  documents,
  isLoading,
}: {
  documents: DocumentListItem[];
  isLoading?: boolean;
}) {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...documents]
      .filter((doc) => matchesFilter(doc, filter))
      .filter((doc) => {
        if (!q) return true;
        return (
          doc.original_filename.toLowerCase().includes(q) ||
          (doc.tender_reference ?? "").toLowerCase().includes(q) ||
          (doc.version_label ?? "").toLowerCase().includes(q)
        );
      })
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
  }, [documents, filter, query]);

  useEffect(() => {
    setPage(1);
  }, [filter, query]);

  const pageItems = useMemo(
    () => paginateSlice(filtered, page, PAGE_SIZE),
    [filtered, page]
  );

  const counts = useMemo(() => {
    const c = { all: documents.length, ready: 0, processing: 0, failed: 0 };
    for (const doc of documents) {
      if (doc.status === "completed") c.ready += 1;
      else if (doc.status === "failed") c.failed += 1;
      else if (
        doc.status === "queued" ||
        ACTIVE_STAGES.includes(doc.status)
      ) {
        c.processing += 1;
      }
    }
    return c;
  }, [documents]);

  if (isLoading) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-surface-border bg-surface" />
    );
  }

  if (!documents.length) {
    return (
      <div className="rounded-lg border border-dashed border-surface-border bg-surface px-6 py-12 text-center">
        <p className="text-sm font-medium text-ink">No documents yet</p>
        <p className="mt-1 text-sm text-ink-muted">
          Upload a tender PDF or DOCX to start parsing and specification analysis.
        </p>
        <Link
          href="/upload"
          className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
        >
          Upload document
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1 rounded-lg border border-surface-border bg-surface p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                filter === f.id
                  ? "bg-surface-muted text-ink"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {f.label}
              <span className="ml-1 tabular-nums text-ink-muted">
                ({counts[f.id]})
              </span>
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Search file or tender…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm outline-none ring-accent focus:ring-1 sm:max-w-xs"
        />
      </div>

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        totalItems={filtered.length}
        onPageChange={setPage}
      />

      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface">
        {filtered.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-ink-muted">
            No documents match this filter.
          </p>
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border bg-surface-muted/80 text-left text-xs font-medium uppercase tracking-wider text-ink-muted">
                <th className="px-4 py-3">Document</th>
                <th className="hidden px-4 py-3 md:table-cell">Tender</th>
                <th className="hidden px-4 py-3 sm:table-cell">Version</th>
                <th className="px-4 py-3">Status</th>
                <th className="hidden px-4 py-3 lg:table-cell">Uploaded</th>
                <th className="w-12 px-4 py-3 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/80">
              {pageItems.map((doc) => (
                <tr key={doc.id} className="hover:bg-surface-muted/40">
                  <td className="px-4 py-3">
                    <Link
                      href={`/documents/${doc.id}/summary`}
                      className="font-medium text-ink hover:text-accent"
                    >
                      {doc.original_filename}
                    </Link>
                    <p className="mt-0.5 text-xs text-ink-muted md:hidden">
                      {doc.tender_reference ?? "—"} · {formatBytes(doc.size_bytes)}
                    </p>
                  </td>
                  <td className="hidden px-4 py-3 text-ink-muted md:table-cell">
                    {doc.tender_reference ?? "—"}
                  </td>
                  <td className="hidden px-4 py-3 text-ink-muted sm:table-cell">
                    {doc.version_label ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="hidden px-4 py-3 text-ink-muted lg:table-cell">
                    {formatDate(doc.created_at)}
                  </td>
                  <td className="relative px-4 py-3 text-right">
                    <DocumentActionsMenu doc={doc} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {filtered.length > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          totalItems={filtered.length}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}
