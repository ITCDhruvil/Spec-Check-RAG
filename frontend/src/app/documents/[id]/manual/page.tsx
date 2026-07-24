"use client";

import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  ManualPdfViewer,
  type ManualPdfHandle,
  type ManualSearchState,
} from "@/components/documents/ManualPdfViewer";
import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";
import { AdminNotePanel } from "@/components/summary/AdminNotePanel";
import { Modal } from "@/components/ui/Modal";
import {
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  NoteIcon,
  RefreshIcon,
  XMarkIcon,
} from "@/components/ui/icons";
import { SpokesLoader } from "@/components/ui/Spokes";
import { truncateFilename } from "@/lib/truncate";
import { getDocument } from "@/lib/api/documents";
import {
  getKeywordFields,
  markDocumentDone,
  resetKeywordFields,
  saveKeywordFields,
  type KeywordField,
} from "@/lib/api/keywords";
import { usePageHeader } from "@/lib/pageHeaderContext";

export default function ManualPage() {
  const params = useParams();
  const documentId = String(params.id);

  const viewerRef = useRef<ManualPdfHandle | null>(null);
  const [fields, setFields] = useState<KeywordField[] | null>(null);
  const [activeKeyword, setActiveKeyword] = useState<string | null>(null);
  const [search, setSearch] = useState<ManualSearchState>({ current: 0, total: 0 });
  const [editing, setEditing] = useState(false);
  const [markingDone, setMarkingDone] = useState(false);
  const [done, setDone] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  // Per-field "checked" markers (visual progress; session-only).
  const [checkedFields, setCheckedFields] = useState<Set<string>>(new Set());

  function toggleFieldChecked(fieldId: string) {
    setCheckedFields((prev) => {
      const next = new Set(prev);
      if (next.has(fieldId)) next.delete(fieldId);
      else next.add(fieldId);
      return next;
    });
  }

  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "completed" || s === "failed" ? false : 3000;
    },
  });

  useQuery({
    queryKey: ["keyword-fields"],
    queryFn: getKeywordFields,
    select: (data) => {
      if (fields === null) setFields(data);
      return data;
    },
  });

  const resolvedFilename =
    documentQuery.data?.tender?.title &&
    documentQuery.data.tender.title !== documentQuery.data.tender.reference_code
      ? documentQuery.data.tender.title
      : documentQuery.data?.original_filename;

  usePageHeader({
    backHref: `/documents/${documentId}/summary`,
    backLabel: "Briefing",
    title: "Manual keyword search",
    subtitle: resolvedFilename,
  });

  const isDone = done || (documentQuery.data?.marked_done ?? false);

  async function toggleDone() {
    if (markingDone) return;
    setMarkingDone(true);
    try {
      const res = await markDocumentDone(documentId, !isDone);
      setDone(res.marked_done);
    } catch {
      window.alert("Could not update status — please try again.");
    } finally {
      setMarkingDone(false);
    }
  }

  function runKeyword(keyword: string) {
    setActiveKeyword(keyword);
    viewerRef.current?.search(keyword);
  }

  async function persist(next: KeywordField[]) {
    setFields(next);
    await saveKeywordFields(next);
  }

  async function handleReset() {
    const defaults = await resetKeywordFields();
    setFields(defaults);
    setActiveKeyword(null);
    viewerRef.current?.clear();
  }

  const leftPanel = (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Fields &amp; keywords</h3>
          <p className="text-xs text-ink-muted">
            Click a keyword to highlight & jump to every occurrence in the PDF.
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setNoteOpen(true)}
            title="Admin note"
            className="flex items-center gap-1.5 rounded border border-surface-border px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:bg-surface-muted"
          >
            <NoteIcon className="h-3.5 w-3.5" />
            Admin note
          </button>
          <button
            type="button"
            onClick={toggleDone}
            disabled={markingDone}
            title={isDone ? "Marked done — click to reopen" : "Mark this document as done"}
            className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
              isDone
                ? "bg-green-100 text-green-800 hover:bg-green-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                : "border border-surface-border text-ink hover:bg-surface-muted"
            }`}
          >
            <CheckIcon className="h-3.5 w-3.5" />
            {isDone ? "Done" : "Mark done"}
          </button>
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              editing ? "bg-accent text-white" : "text-ink-muted hover:bg-surface-muted"
            }`}
          >
            {editing ? "Save" : "Edit"}
          </button>
          <button
            type="button"
            onClick={handleReset}
            title="Reset to default keywords"
            className="flex h-7 w-7 items-center justify-center rounded text-ink-muted hover:bg-surface-muted"
          >
            <RefreshIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Match stepper for the active keyword */}
      {activeKeyword && (
        <div className="mb-3 flex shrink-0 items-center justify-between rounded-md border border-surface-border bg-surface-muted/50 px-3 py-2 text-xs">
          <span className="min-w-0 truncate font-medium">
            “{activeKeyword}” —{" "}
            {search.total > 0
              ? `${search.current} of ${search.total}`
              : "no matches"}
          </span>
          {search.total > 0 && (
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => viewerRef.current?.prev()}
                className="flex h-6 w-6 items-center justify-center rounded hover:bg-surface"
                title="Previous match"
              >
                <ChevronLeftIcon className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => viewerRef.current?.next()}
                className="flex h-6 w-6 items-center justify-center rounded hover:bg-surface"
                title="Next match"
              >
                <ChevronRightIcon className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {fields === null ? (
        <SpokesLoader className="py-10" />
      ) : (
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {fields.map((f) => (
            <FieldCard
              key={f.id}
              field={f}
              activeKeyword={activeKeyword}
              editing={editing}
              checked={checkedFields.has(f.id)}
              onToggleChecked={() => toggleFieldChecked(f.id)}
              onKeyword={runKeyword}
              onChange={(updated) =>
                persist(fields.map((x) => (x.id === f.id ? updated : x)))
              }
              onRemove={() => persist(fields.filter((x) => x.id !== f.id))}
            />
          ))}
          {editing && (
            <button
              type="button"
              onClick={() =>
                persist([
                  ...fields,
                  { id: `custom_${Date.now()}`, label: "New field", keywords: [] },
                ])
              }
              className="mt-1 w-full rounded-md border border-dashed border-surface-border px-3 py-2 text-xs text-ink-muted hover:border-accent/40 hover:text-ink"
            >
              + Add field
            </button>
          )}
        </div>
      )}
    </div>
  );

  const rightPanel = (
    <ManualPdfViewer
      ref={viewerRef}
      documentId={documentId}
      onSearchState={setSearch}
    />
  );

  return (
    <>
      <SplitPanelLayout left={leftPanel} right={rightPanel} />
      <Modal
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        blurBackdrop
        maxWidth="max-w-2xl"
      >
        <div className="px-3 pb-3 pt-3">
          {noteOpen && (
            <AdminNotePanel
              documentId={documentId}
              bare
              docName={truncateFilename(resolvedFilename ?? "", 48)}
            />
          )}
        </div>
      </Modal>
    </>
  );
}

function FieldCard({
  field,
  activeKeyword,
  editing,
  checked,
  onToggleChecked,
  onKeyword,
  onChange,
  onRemove,
}: {
  field: KeywordField;
  activeKeyword: string | null;
  editing: boolean;
  checked: boolean;
  onToggleChecked: () => void;
  onKeyword: (keyword: string) => void;
  onChange: (f: KeywordField) => void;
  onRemove: () => void;
}) {
  const [newKw, setNewKw] = useState("");

  if (editing) {
    return (
      <div className="rounded-md border border-surface-border bg-surface px-3 py-2">
        <div className="flex items-center gap-2">
          <input
            value={field.label}
            onChange={(e) => onChange({ ...field, label: e.target.value })}
            className="min-w-0 flex-1 rounded border border-surface-border bg-surface px-2 py-1 text-sm text-ink"
          />
          <button
            type="button"
            onClick={onRemove}
            title="Remove field"
            className="text-ink-muted hover:text-red-600"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {field.keywords.map((k, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2 py-0.5 text-xs"
            >
              {k}
              <button
                type="button"
                onClick={() =>
                  onChange({
                    ...field,
                    keywords: field.keywords.filter((_, idx) => idx !== i),
                  })
                }
                className="text-ink-muted hover:text-red-600"
              >
                <XMarkIcon className="h-3 w-3" />
              </button>
            </span>
          ))}
          <input
            value={newKw}
            onChange={(e) => setNewKw(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newKw.trim()) {
                onChange({ ...field, keywords: [...field.keywords, newKw.trim()] });
                setNewKw("");
              }
            }}
            placeholder="+ keyword"
            className="w-24 rounded border border-surface-border bg-surface px-1.5 py-0.5 text-xs text-ink"
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-md border px-3 py-2 transition-colors ${
        checked
          ? "border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10"
          : "border-surface-border bg-surface"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-ink">{field.label}</p>
        <button
          type="button"
          onClick={onToggleChecked}
          title={checked ? "Mark as not done" : "Mark this field as done"}
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors ${
            checked
              ? "border-emerald-500 bg-emerald-500 text-white"
              : "border-surface-border text-ink-muted hover:border-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300"
          }`}
        >
          <CheckIcon className="h-3 w-3" />
        </button>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {field.keywords.map((k, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onKeyword(k)}
            className={`rounded px-2 py-0.5 text-[11px] transition-colors ${
              activeKeyword === k
                ? "bg-accent text-white"
                : "bg-surface-muted text-ink-muted hover:bg-accent/10 hover:text-accent"
            }`}
          >
            {k}
          </button>
        ))}
        {!field.keywords.length && (
          <span className="text-[11px] italic text-ink-muted">No keywords</span>
        )}
      </div>
    </div>
  );
}
