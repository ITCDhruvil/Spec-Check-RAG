"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { DashboardStats } from "@/components/dashboard/DashboardStats";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { listDocuments } from "@/lib/api/documents";
import { ACTIVE_STAGES } from "@/lib/types/document";

export default function DashboardPage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["documents"],
    queryFn: () => listDocuments(),
    refetchInterval: (query) => {
      const docs = query.state.data?.results ?? [];
      const hasActive = docs.some(
        (d) => d.status === "queued" || ACTIVE_STAGES.includes(d.status)
      );
      return hasActive ? 5000 : false;
    },
  });

  const documents = data?.results ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Dashboard</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-muted">
            Upload tender documents and open specification briefings when they are
            ready.
          </p>
        </div>
        <Link
          href="/upload"
          className="shrink-0 rounded-md bg-accent px-4 py-2 text-center text-sm font-medium text-white hover:bg-accent-hover"
        >
          Upload document
        </Link>
      </div>

      {isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {(error as Error).message}
        </div>
      )}

      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-lg border border-surface-border bg-surface"
            />
          ))}
        </div>
      ) : (
        documents.length > 0 && <DashboardStats documents={documents} />
      )}

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">Documents</h3>
        <DocumentTable documents={documents} isLoading={isPending} />
      </section>
    </div>
  );
}
