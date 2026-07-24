"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { CheckIcon } from "@/components/ui/icons";
import { SpokesLoader } from "@/components/ui/Spokes";
import { getAdminNote, saveAdminNote } from "@/lib/api/documents";

/** Editable one-paragraph note summarizing extraction results + corrections.
 * Auto-fills with a generated draft; the user can edit before saving. */
export function AdminNotePanel({
  documentId,
  bare = false,
  docName,
}: {
  documentId: string;
  /** Render without the outer card chrome (for use inside a modal). */
  bare?: boolean;
  /** Document display name shown next to the title (modal usage). */
  docName?: string;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  const query = useQuery({
    queryKey: ["admin-note", documentId],
    queryFn: () => getAdminNote(documentId),
  });

  // Initialize editor: saved note wins; otherwise the generated draft.
  useEffect(() => {
    if (!query.data || dirty) return;
    setText(query.data.note || query.data.draft || "");
  }, [query.data, dirty]);

  const saveMutation = useMutation({
    mutationFn: (note: string) => saveAdminNote(documentId, note),
    onSuccess: () => {
      // Refetch instead of patching the cache — keeps note/draft/updated_by
      // consistent with the server in one place.
      queryClient.invalidateQueries({ queryKey: ["admin-note", documentId] });
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  const isDraft = Boolean(query.data && !query.data.note && !dirty);

  const savedInfo = query.data?.updated_at ? (
    <p className="flex shrink-0 items-center gap-2 text-xs text-ink-muted">
      <span>
        Saved {new Date(query.data.updated_at).toLocaleString("en-US", {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })}
      </span>
      <span className="h-3.5 w-px bg-surface-border" aria-hidden />
      <span>by {query.data.updated_by ?? "—"}</span>
    </p>
  ) : null;

  return (
    <div className={bare ? "" : "rounded-lg border border-surface-border bg-surface"}>
      {/* Header: title + document name on the left, saved-by on the right. */}
      <div
        className={`flex items-center justify-between gap-4 border-b border-surface-border ${
          bare ? "px-1 pb-2.5" : "px-5 py-3"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <h3 className="shrink-0 text-sm font-semibold">Admin note</h3>
          {docName && (
            <span className="truncate text-xs text-ink-muted" title={docName}>
              {docName}
            </span>
          )}
          {isDraft && (
            <span className="shrink-0 rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
              Auto-generated draft
            </span>
          )}
        </div>
        {savedInfo}
      </div>

      <div className={bare ? "px-1 pt-3" : "p-5"}>
        {query.isPending ? (
          <SpokesLoader className="py-6" />
        ) : query.isError ? (
          <p className="text-sm text-red-600 dark:text-red-300">{(query.error as Error).message}</p>
        ) : (
          <>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setDirty(true);
              }}
              rows={4}
              placeholder="Summary of extraction results and corrections for this document…"
              className="w-full resize-y rounded-md border border-surface-border bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />
            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                onClick={() => saveMutation.mutate(text)}
                disabled={saveMutation.isPending || !text.trim()}
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
              >
                {saveMutation.isPending ? "Saving…" : "Save note"}
              </button>
              {query.data?.draft && (
                <button
                  type="button"
                  onClick={() => {
                    setText(query.data!.draft || "");
                    setDirty(true);
                  }}
                  className="rounded-md px-3 py-2 text-xs text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
                  title="Replace the editor content with a freshly generated draft"
                >
                  Regenerate draft
                </button>
              )}
              {saved && (
                <span className="inline-flex items-center gap-1 text-sm text-emerald-700 dark:text-emerald-300">
                  <CheckIcon className="h-4 w-4" /> Saved
                </span>
              )}
              {saveMutation.isError && (
                <span className="text-sm text-red-600 dark:text-red-300">
                  {(saveMutation.error as Error).message}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
