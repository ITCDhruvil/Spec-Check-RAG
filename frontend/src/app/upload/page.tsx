"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { TextShimmer } from "@/components/ui/TextShimmer";
import { UploadDropzone } from "@/components/upload/UploadDropzone";
import {
  deleteDocument,
  DuplicateDocumentError,
  uploadDocument,
  type DuplicateDocumentInfo,
} from "@/lib/api/documents";
import { truncateFilename } from "@/lib/truncate";
import type { DocumentVersionType } from "@/lib/types/document";

const VERSION_TYPES: { value: DocumentVersionType; label: string }[] = [
  { value: "original", label: "Original tender / specification" },
  { value: "revision", label: "Revision" },
  { value: "corrigendum", label: "Corrigendum" },
  { value: "addendum", label: "Addendum" },
  { value: "clarification", label: "Clarification" },
  { value: "annexure", label: "Annexure" },
  { value: "other", label: "Other" },
];

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export default function UploadPage() {
  const router = useRouter();
  const [progress, setProgress] = useState(0);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<number | null>(null);
  const [tenderReference, setTenderReference] = useState("");
  const [tenderTitle, setTenderTitle] = useState("");
  const [versionType, setVersionType] = useState<DocumentVersionType>("original");
  const [versionLabel, setVersionLabel] = useState("");

  const [duplicate, setDuplicate] = useState<DuplicateDocumentInfo | null>(null);
  const [deletingDup, setDeletingDup] = useState(false);
  // Keep the rejected file so "Delete existing & re-upload" can re-send it
  // immediately without the user dropping it again.
  const pendingFileRef = useRef<File | null>(null);
  // Uploaded doc id — presents the AI-extraction / manual-search choice.
  const [uploadedId, setUploadedId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (file: File) =>
      uploadDocument({
        file,
        tenderReference: tenderReference.trim() || undefined,
        tenderTitle: tenderTitle.trim() || undefined,
        versionType,
        versionLabel: versionLabel.trim() || undefined,
        onProgress: setProgress,
      }),
    onSuccess: (data) => {
      pendingFileRef.current = null;
      setUploadedId(data.id);
    },
    onError: (err) => {
      if (err instanceof DuplicateDocumentError) {
        setDuplicate(err.existing);
      }
    },
  });

  async function handleDeleteDuplicate() {
    if (!duplicate || deletingDup) return;
    setDeletingDup(true);
    try {
      await deleteDocument(duplicate.id);
      setDuplicate(null);
      mutation.reset();
      // Instantly re-upload the same file the user just tried.
      const file = pendingFileRef.current;
      if (file) {
        setProgress(0);
        mutation.mutate(file);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Could not delete the document.");
    } finally {
      setDeletingDup(false);
    }
  }

  const handleFile = (file: File) => {
    if (!tenderTitle.trim()) return; // dropzone is disabled, but belt-and-braces
    setDuplicate(null);
    pendingFileRef.current = file;
    setSelectedName(file.name);
    setSelectedSize(file.size);
    setProgress(0);
    mutation.mutate(file);
  };

  // 100% uploaded but response pending = server-side finalization (virus/MIME
  // check, DB writes). Distinguish it so the bar never looks stuck.
  const finalizing = mutation.isPending && progress >= 100;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Upload tender document</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Upload a PDF or Word file. We will read it and prepare a specification briefing
          for you automatically.
        </p>
      </div>

      {/* Title is required — it becomes the document's display name everywhere. */}
      <div className="rounded-lg border border-surface-border bg-surface p-4">
        <label className="block text-sm">
          <span className="font-medium text-ink">
            Tender title <span className="text-red-600">*</span>
          </span>
          <input
            type="text"
            required
            placeholder="e.g. HVAC Controls Replacement — Rock Hill Schools"
            value={tenderTitle}
            onChange={(e) => setTenderTitle(e.target.value)}
            className="mt-1.5 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent"
            disabled={mutation.isPending}
          />
          <span className="mt-1 block text-xs text-ink-muted">
            Used as the document name across the dashboard, briefing, and exports.
          </span>
        </label>
      </div>

      {uploadedId ? (
        <div className="rounded-lg border border-surface-border bg-surface p-6">
          <p className="text-sm font-semibold text-ink">
            Uploaded — how do you want to work with this document?
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            {tenderTitle.trim() || selectedName}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => router.push(`/documents/${uploadedId}/summary`)}
              className="rounded-lg border border-accent/30 bg-accent/5 p-4 text-left transition-colors hover:border-accent/50 hover:bg-accent/10"
            >
              <p className="text-sm font-semibold text-accent">AI Extraction</p>
              <p className="mt-1 text-xs text-ink-muted">
                Automatically read the document and build a full specification
                briefing with every field.
              </p>
            </button>
            <button
              type="button"
              onClick={() => router.push(`/documents/${uploadedId}/manual`)}
              className="relative rounded-lg border border-surface-border bg-surface p-4 text-left transition-colors hover:border-accent/40 hover:bg-surface-muted/40"
            >
              <span className="absolute right-3 top-3 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300">
                Faster
              </span>
              <p className="text-sm font-semibold text-ink">Manual Search</p>
              <p className="mt-1 text-xs text-ink-muted">
                Jump straight to keywords in the PDF and copy values yourself —
                no waiting for AI analysis.
              </p>
            </button>
          </div>
          <button
            type="button"
            onClick={() => {
              setUploadedId(null);
              setSelectedName(null);
              setTenderTitle("");
              mutation.reset();
            }}
            className="mt-4 text-xs text-ink-muted hover:text-ink"
          >
            Upload another document
          </button>
        </div>
      ) : (
        <>
          <UploadDropzone
            onFileSelected={handleFile}
            disabled={mutation.isPending || !tenderTitle.trim()}
          />
          {!tenderTitle.trim() && (
            <p className="-mt-3 text-xs text-ink-muted">
              Enter a tender title above to enable upload.
            </p>
          )}
        </>
      )}

      {mutation.isPending && (
        <div className="space-y-2 rounded-lg border border-surface-border bg-surface p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 truncate text-sm font-medium">
              <TextShimmer>
                {finalizing
                  ? `Finalizing ${selectedName ?? "document"}…`
                  : `Uploading ${selectedName ?? "document"}…`}
              </TextShimmer>
            </p>
            <p className="shrink-0 text-xs tabular-nums text-ink-muted">
              {selectedSize != null
                ? `${formatBytes((progress / 100) * selectedSize)} / ${formatBytes(selectedSize)}`
                : `${progress}%`}
            </p>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
            <div
              className={`h-full bg-accent transition-all ${finalizing ? "animate-pulse" : ""}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          {finalizing && (
            <p className="text-xs text-ink-muted">
              Upload complete — verifying and saving on the server…
            </p>
          )}
        </div>
      )}

      {duplicate ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-4 dark:border-amber-500/30 dark:bg-amber-500/10">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
            This document already exists
          </p>
          <p
            className="mt-1 text-sm text-amber-700 dark:text-amber-200"
            title={duplicate.original_filename}
          >
            {duplicate.tender_title || truncateFilename(duplicate.original_filename, 56)}
            <span className="ml-2 text-xs text-amber-700/80 dark:text-amber-300/90">
              (status: {duplicate.status}, uploaded{" "}
              {new Date(duplicate.created_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
              )
            </span>
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => router.push(`/documents/${duplicate.id}/summary`)}
              className="rounded-md bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:bg-accent-hover"
            >
              View document
            </button>
            <button
              type="button"
              onClick={handleDeleteDuplicate}
              disabled={deletingDup}
              className="rounded-md border border-red-200 bg-surface px-3.5 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10"
            >
              {deletingDup ? "Deleting & re-uploading…" : "Delete existing & re-upload"}
            </button>
            <button
              type="button"
              onClick={() => { setDuplicate(null); mutation.reset(); }}
              className="px-2 py-1.5 text-xs text-amber-700 hover:text-amber-900 dark:text-amber-200 dark:hover:text-amber-100"
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : mutation.isError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {mutation.error.message}
        </div>
      ) : null}

      <details className="rounded-lg border border-surface-border bg-surface">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-ink-muted hover:text-ink">
          Optional: tender reference & version
        </summary>
        <div className="space-y-4 border-t border-surface-border px-4 py-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-ink-muted">Tender reference</span>
              <input
                type="text"
                placeholder="TENDER-2026-0142"
                value={tenderReference}
                onChange={(e) => setTenderReference(e.target.value)}
                className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
                disabled={mutation.isPending}
              />
            </label>
            <label className="block text-sm">
              <span className="text-ink-muted">Version type</span>
              <select
                value={versionType}
                onChange={(e) => setVersionType(e.target.value as DocumentVersionType)}
                className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
                disabled={mutation.isPending}
              >
                {VERSION_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-ink-muted">Version label</span>
              <input
                type="text"
                placeholder="Corrigendum A"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
                className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
                disabled={mutation.isPending}
              />
            </label>
          </div>
          <p className="text-xs text-ink-muted">
            Leave blank to auto-create a package ID. Use the same reference for
            corrigendums and revisions.
          </p>
        </div>
      </details>
    </div>
  );
}
