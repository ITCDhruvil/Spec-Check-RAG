"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { UploadDropzone } from "@/components/upload/UploadDropzone";
import { uploadDocument } from "@/lib/api/documents";
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

export default function UploadPage() {
  const router = useRouter();
  const [progress, setProgress] = useState(0);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [tenderReference, setTenderReference] = useState("");
  const [tenderTitle, setTenderTitle] = useState("");
  const [versionType, setVersionType] = useState<DocumentVersionType>("original");
  const [versionLabel, setVersionLabel] = useState("");

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
      router.push(`/documents/${data.id}/summary`);
    },
  });

  const handleFile = (file: File) => {
    setSelectedName(file.name);
    setProgress(0);
    mutation.mutate(file);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Upload tender document</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Upload a PDF or Word file. We will read it and prepare a specification briefing
          for you automatically.
        </p>
      </div>

      <UploadDropzone onFileSelected={handleFile} disabled={mutation.isPending} />

      {mutation.isPending && (
        <div className="space-y-2 rounded-lg border border-surface-border bg-surface p-4">
          <p className="text-sm font-medium">
            Uploading {selectedName ?? "document"}…
          </p>
          <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {mutation.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {mutation.error.message}
        </div>
      )}

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
                className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm"
                disabled={mutation.isPending}
              />
            </label>
            <label className="block text-sm">
              <span className="text-ink-muted">Tender title</span>
              <input
                type="text"
                value={tenderTitle}
                onChange={(e) => setTenderTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm"
                disabled={mutation.isPending}
              />
            </label>
            <label className="block text-sm">
              <span className="text-ink-muted">Version type</span>
              <select
                value={versionType}
                onChange={(e) => setVersionType(e.target.value as DocumentVersionType)}
                className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm"
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
                className="mt-1 w-full rounded-md border border-surface-border px-3 py-2 text-sm"
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
