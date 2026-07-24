"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { SimpleProcessingCard } from "@/components/documents/SimpleProcessingCard";
import { DocumentPreview } from "@/components/documents/DocumentPreview";
import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { PdfNavigationProvider } from "@/lib/pdfNavigationContext";
import { AdminNotePanel } from "@/components/summary/AdminNotePanel";
import { SummaryViewer } from "@/components/summary/SummaryViewer";
import { SummaryPageSkeleton } from "@/components/summary/SummaryPageSkeleton";
import { MaintenanceBanner } from "@/components/summary/MaintenanceBanner";
import { useClientMounted } from "@/lib/useClientMounted";
import { getDocument, kickDocumentProcessing } from "@/lib/api/documents";
import {
  useCachedDocumentMeta,
} from "@/lib/documentMetaCache";
import {
  cancelSummary,
  generateSummary,
  getSummary,
  getSummaryStatus,
  regenerateSummary,
  repairSpecCheck,
} from "@/lib/api/intelligence";
import { resolveUserProcessingPhase } from "@/lib/userFacingStatus";

const PROCESSING_STAGES = [
  "chunking_processing",
  "embedding_processing",
  "extraction_processing",
  "summary_processing",
];

export default function SummaryPage() {
  const mounted = useClientMounted();
  const params = useParams();
  const router = useRouter();
  const documentId = String(params.id);
  const queryClient = useQueryClient();
  const autoGenerateStarted = useRef(false);
  const kickStarted = useRef(false);
  const queuedSince = useRef<number | null>(null);
  const { cachedMeta, persistMeta } = useCachedDocumentMeta(documentId);

  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
  });

  useEffect(() => {
    const doc = documentQuery.data;
    if (!doc?.original_filename || !doc.mime_type) return;
    persistMeta({
      original_filename: doc.original_filename,
      mime_type: doc.mime_type,
    });
  }, [documentId, documentQuery.data, persistMeta]);

  const statusQuery = useQuery({
    queryKey: ["summary-status", documentId],
    queryFn: () => getSummaryStatus(documentId),
    refetchInterval: (q) => {
      const data = q.state.data;
      const st = data?.summary_status;
      const docSt = data?.document_status;
      if (st === "completed" || st === "failed") {
        return docSt === "completed" ? false : 3000;
      }
      if (
        st === "processing" ||
        PROCESSING_STAGES.includes(data?.progress_stage ?? "") ||
        docSt !== "completed"
      ) {
        return 3000;
      }
      return false;
    },
  });

  const summaryQuery = useQuery({
    queryKey: ["summary", documentId],
    queryFn: () => getSummary(documentId),
    enabled: statusQuery.data?.summary_status === "completed",
    retry: false,
  });

  const generateMutation = useMutation({
    mutationFn: () => generateSummary(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
    },
  });

  const regenerateMutation = useMutation({
    mutationFn: () => regenerateSummary(documentId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
      queryClient.invalidateQueries({ queryKey: ["summary", documentId] });
      if (data && "sync" in data && (data as { sync?: boolean }).sync) {
        queryClient.refetchQueries({ queryKey: ["summary-status", documentId] });
      }
    },
  });

  const repairMutation = useMutation({
    mutationFn: () => repairSpecCheck(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["summary", documentId] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSummary(documentId),
    onSettled: () => {
      // Bust the document list cache so the dashboard badge shows "Failed"
      // immediately without waiting for the next 5 s poll.
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
      router.push("/");
    },
  });

  useEffect(() => {
    if (statusQuery.data?.summary_status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["summary", documentId] });
    }
  }, [statusQuery.data?.summary_status, documentId, queryClient]);

  const docStatus = statusQuery.data?.document_status;
  const summaryStatus = statusQuery.data?.summary_status;
  const isWorking =
    regenerateMutation.isPending ||
    generateMutation.isPending ||
    summaryStatus === "processing" ||
    PROCESSING_STAGES.includes(statusQuery.data?.progress_stage ?? "") ||
    (docStatus === "completed" &&
      summaryStatus !== "completed" &&
      summaryStatus !== "failed");

  const hasSummary = summaryStatus === "completed";
  const phase = resolveUserProcessingPhase(docStatus, summaryStatus, {
    summaryStarting: generateMutation.isPending || regenerateMutation.isPending,
  });

  useEffect(() => {
    if (autoGenerateStarted.current) return;
    if (!statusQuery.data) return;
    if (docStatus !== "completed") return;
    if (summaryStatus === "completed" || summaryStatus === "processing") return;

    autoGenerateStarted.current = true;
    generateMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when parse completes
  }, [docStatus, summaryStatus, statusQuery.data]);

  useEffect(() => {
    if (docStatus !== "queued" && docStatus !== "uploaded") {
      queuedSince.current = null;
      return;
    }
    if (queuedSince.current === null) {
      queuedSince.current = Date.now();
    }
    if (kickStarted.current) return;

    const elapsed = Date.now() - (queuedSince.current ?? Date.now());
    if (elapsed < 12000) return;

    kickStarted.current = true;
    kickDocumentProcessing(documentId)
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
        queryClient.invalidateQueries({ queryKey: ["document-status", documentId] });
      })
      .catch(() => {
        kickStarted.current = false;
      });
  }, [docStatus, documentId, queryClient]);

  const resolvedFilename =
    documentQuery.data?.original_filename ??
    cachedMeta?.original_filename ??
    "Your document";
  const resolvedMimeType =
    documentQuery.data?.mime_type ?? cachedMeta?.mime_type;
  // Tender title (user-given) is the preferred display name everywhere.
  const tenderTitle = documentQuery.data?.tender?.title;
  const displayName =
    tenderTitle && tenderTitle !== documentQuery.data?.tender?.reference_code
      ? tenderTitle
      : resolvedFilename;

  // PDF download menu + "Ask questions" CTA temporarily hidden from this page.
  // BriefingDownloadMenu and /documents/[id]/chat remain available to re-enable.
  // Page header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "Specification briefing",
    subtitle: displayName,
  });

  const briefingPanel = (
    <div className="space-y-6">
      <MaintenanceBanner />
      {(generateMutation.isError || regenerateMutation.isError) && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {(generateMutation.error ?? regenerateMutation.error)?.message}
        </div>
      )}

      {statusQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {(statusQuery.error as Error).message}
        </div>
      )}

      {statusQuery.isPending && !statusQuery.isError && (
        <div className="rounded-lg border border-surface-border bg-surface p-6">
          <div className="flex items-center gap-3">
            <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-surface-muted" />
            <div className="h-4 w-48 animate-pulse rounded bg-surface-muted" />
          </div>
          <div className="mt-5 h-1.5 w-full animate-pulse rounded-full bg-surface-muted" />
        </div>
      )}

      {!hasSummary && !statusQuery.isPending && (
        <SimpleProcessingCard
          documentStatus={docStatus}
          summaryStatus={summaryStatus}
          summaryStarting={
            generateMutation.isPending || regenerateMutation.isPending
          }
          waitingToStart={
            (docStatus === "queued" || docStatus === "uploaded") &&
            kickStarted.current
          }
          progressStage={statusQuery.data?.progress_stage}
          errorMessage={statusQuery.data?.error_message}
          onStop={() => cancelMutation.mutate()}
        />
      )}

      {summaryStatus === "failed" && (() => {
        const wasCancelled = statusQuery.data?.error_message
          ?.toLowerCase()
          .includes("cancel");
        return (
          <div
            className={`flex flex-wrap items-center gap-3 rounded-md border px-4 py-3 text-sm ${
              wasCancelled
                ? "border-surface-border bg-surface text-ink-muted"
                : "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
            }`}
          >
            <p className="flex-1">
              {wasCancelled
                ? "Processing was stopped. You can restart from the beginning."
                : (statusQuery.data?.error_message ??
                  "We could not build the briefing for this document.")}
            </p>
            <button
              type="button"
              onClick={() => {
                autoGenerateStarted.current = false;
                kickStarted.current = false;
                queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
                kickDocumentProcessing(documentId)
                  .then(() => {
                    queryClient.invalidateQueries({ queryKey: ["summary-status", documentId] });
                    queryClient.invalidateQueries({ queryKey: ["document", documentId] });
                  })
                  .catch(() => {
                    autoGenerateStarted.current = false;
                    generateMutation.mutate();
                  });
              }}
              disabled={generateMutation.isPending}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ring-1 disabled:opacity-50 ${
                wasCancelled
                  ? "bg-surface-muted text-ink ring-surface-border hover:bg-surface"
                  : "bg-surface text-red-600 ring-red-200 hover:bg-red-50 dark:text-red-300 dark:ring-red-500/30 dark:hover:bg-red-500/10"
              }`}
            >
              {generateMutation.isPending
                ? "Starting…"
                : wasCancelled
                  ? "Restart processing"
                  : "Try again"}
            </button>
          </div>
        );
      })()}

      {hasSummary && summaryQuery.isPending && (
        <p className="text-sm text-ink-muted">Loading your briefing…</p>
      )}

      {hasSummary && summaryQuery.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {(summaryQuery.error as Error).message}
        </div>
      )}

      {/* Repair banner — shown when summary exists but spec_check_fields is empty */}
      {summaryQuery.data && (() => {
        const spec = summaryQuery.data.summary_json.spec_check_fields;
        const hasSpec = Boolean(
          spec?.project_metadata_items?.length ||
            spec?.project_people_items?.length ||
            spec?.project_size_location_items?.length ||
            spec?.project_dates?.length ||
            spec?.bond_items?.length
        );
        if (hasSpec) return null;
        return (
          <div className="flex flex-wrap items-start gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm dark:border-amber-500/30 dark:bg-amber-500/10">
            <div className="flex-1">
              <p className="font-medium text-amber-800 dark:text-amber-300">Spec-check register is empty</p>
              <p className="mt-0.5 text-amber-700 dark:text-amber-200">
                Project identity, dates, and bond fields were not extracted into the
                spec-check register. Click &ldquo;Build&rdquo; to populate them from the
                existing extraction data — no re-processing required.
              </p>
              {repairMutation.isError && (
                <p className="mt-1 text-red-700 dark:text-red-300">
                  {(repairMutation.error as Error).message}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => repairMutation.mutate()}
              disabled={repairMutation.isPending}
              className="mt-0.5 shrink-0 rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {repairMutation.isPending ? "Building…" : "Build spec-check fields"}
            </button>
          </div>
        );
      })()}

      {summaryQuery.data && (
        <SummaryViewer data={summaryQuery.data.summary_json} />
      )}

      {hasSummary && <AdminNotePanel documentId={documentId} />}

      {statusQuery.isPending && phase !== "ready" && (
        <p className="sr-only">Loading status…</p>
      )}
    </div>
  );

  const previewPanel = (
    <div className="h-full min-h-0">
      <DocumentPreview
        documentId={documentId}
        filename={resolvedFilename !== "Your document" ? resolvedFilename : undefined}
        mimeType={resolvedMimeType}
      />
    </div>
  );

  if (!mounted) {
    return (
      <PdfNavigationProvider>
        <SummaryPageSkeleton />
      </PdfNavigationProvider>
    );
  }

  return (
    <PdfNavigationProvider>
      <SplitPanelLayout left={briefingPanel} right={previewPanel} />
    </PdfNavigationProvider>
  );
}
