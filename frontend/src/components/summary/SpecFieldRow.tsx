"use client";

import { useState } from "react";
import { useParams } from "next/navigation";

import { getAllCitationTargets, getPrimaryCitationTarget } from "@/lib/citationTargets";
import { copyToClipboard } from "@/lib/copyToClipboard";
import { usePdfNavigation } from "@/lib/pdfNavigationContext";
import { resolveFieldLabel, resolveFieldValue } from "@/lib/specFieldLabels";
import type { SourceCitation, SummarySectionBlock } from "@/lib/types/intelligence";
import { submitFieldFeedback } from "@/lib/api/intelligence";

import { CitationPanel, CitationToggle } from "./SourceCitationList";

const ISSUE_OPTIONS = [
  { value: "wrong_value", label: "Wrong value extracted" },
  { value: "wrong_source", label: "Wrong source / citation" },
  { value: "missing", label: "Value is missing from result" },
  { value: "other", label: "Other" },
];

/** Jump to verified citation in document. */
function JumpButton({ onClick }: { onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Jump to source in document"
      aria-label="Jump to source in document"
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 transition-colors hover:border-emerald-400 hover:bg-emerald-100 active:bg-emerald-200"
    >
      <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M2 6h6M6.5 3.5L9 6l-2.5 2.5" />
      </svg>
    </button>
  );
}

function CopyValueButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyToClipboard(value);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? "Copied" : "Copy value"}
      aria-label={copied ? "Copied" : "Copy value"}
      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors ${
        copied
          ? "border-emerald-300 bg-emerald-50 text-emerald-600"
          : "border-surface-border text-ink-muted hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
      }`}
    >
      {copied ? (
        <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M2 6.5L5 9.5L10 3.5" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
          <rect x="5" y="5" width="8" height="8" rx="1" />
          <path d="M5 11H4a2 2 0 01-2-2V4a2 2 0 012-2h5a2 2 0 012 2v1" />
        </svg>
      )}
    </button>
  );
}

function UnverifiedBadge() {
  return (
    <span
      title="No verified source found for this field"
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-amber-200 bg-amber-50 text-amber-600"
    >
      <svg className="h-3.5 w-3.5" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="5" cy="5" r="3.5" />
        <path d="M5 3.2v2M5 6.8h.01" />
      </svg>
    </span>
  );
}

/** Correct / wrong feedback buttons — circular icon-only. */
function FeedbackButtons({
  onUp,
  onDown,
  submitted,
}: {
  onUp: () => void;
  onDown: () => void;
  submitted: "up" | "down" | null;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={onUp}
        title="This field is correct"
        aria-label="Mark field as correct"
        disabled={submitted !== null}
        className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${
          submitted === "up"
            ? "border-emerald-300 bg-emerald-50 text-emerald-600"
            : "border-surface-border text-ink-muted hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-600"
        } disabled:opacity-40`}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M2 6.5L5 9.5L10 3.5" />
        </svg>
      </button>
      <button
        type="button"
        onClick={onDown}
        title="Something is wrong with this field"
        aria-label="Mark field as incorrect"
        disabled={submitted !== null}
        className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${
          submitted === "down"
            ? "border-red-300 bg-red-50 text-red-600"
            : "border-surface-border text-ink-muted hover:border-red-300 hover:bg-red-50 hover:text-red-500"
        } disabled:opacity-40`}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M3 3l6 6M9 3l-6 6" />
        </svg>
      </button>
    </span>
  );
}

/** Inline correction form shown after 👎. */
function CorrectionForm({
  fieldLabel,
  extractedValue,
  onSubmit,
  onDismiss,
}: {
  fieldLabel: string;
  extractedValue: string;
  onSubmit: (data: { issue_type: string; correct_value: string; comment: string }) => Promise<void>;
  onDismiss: () => void;
}) {
  const [issueType, setIssueType] = useState("wrong_value");
  const [correctValue, setCorrectValue] = useState("");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({ issue_type: issueType, correct_value: correctValue, comment });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-2 rounded-lg border border-red-100 bg-red-50/60 px-3 py-3 text-xs"
    >
      <p className="mb-2 font-semibold text-red-800">What's wrong with "{fieldLabel}"?</p>

      <div className="mb-2">
        <select
          value={issueType}
          onChange={(e) => setIssueType(e.target.value)}
          className="w-full rounded border border-surface-border bg-white px-2 py-1.5 text-xs text-ink"
        >
          {ISSUE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {issueType !== "missing" && (
        <div className="mb-2">
          <label className="mb-1 block text-ink-muted">What is the correct value?</label>
          <input
            type="text"
            value={correctValue}
            onChange={(e) => setCorrectValue(e.target.value)}
            placeholder={extractedValue ? `Currently: ${extractedValue.slice(0, 60)}` : "Enter correct value"}
            className="w-full rounded border border-surface-border bg-white px-2 py-1.5 text-xs text-ink placeholder:text-ink-muted/60"
          />
        </div>
      )}

      <div className="mb-3">
        <label className="mb-1 block text-ink-muted">Additional context (optional)</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          placeholder="Any extra context…"
          className="w-full resize-none rounded border border-surface-border bg-white px-2 py-1.5 text-xs text-ink placeholder:text-ink-muted/60"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Submit feedback"}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="text-ink-muted hover:text-ink"
        >
          Cancel
        </button>
      </div>
      <p className="mt-2 text-[10px] text-ink-muted/70">
        Your correction helps improve future extractions automatically.
      </p>
    </form>
  );
}

export function SpecFieldRow({
  item,
  extractionType,
  valueAsSubtext = false,
  confidenceBadge,
}: {
  item: SummarySectionBlock;
  /** Extraction type key used for feedback routing (e.g. "submission_deadlines"). */
  extractionType?: string;
  /** When true, bond-style: label from text, value from date field. */
  valueAsSubtext?: boolean;
  confidenceBadge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [feedbackState, setFeedbackState] = useState<"idle" | "form" | "done">("idle");
  const [submitted, setSubmitted] = useState<"up" | "down" | null>(null);
  const { jumpToCitations, canJump } = usePdfNavigation();
  const params = useParams();
  const documentId = params?.id ? String(params.id) : null;

  const sources = item.sources;
  const hasCitations = Boolean(sources?.length);
  const primaryTarget = hasCitations
    ? getPrimaryCitationTarget(sources as SourceCitation[])
    : null;
  const allTargets = hasCitations
    ? getAllCitationTargets(sources as SourceCitation[])
    : [];
  const hasVerified = hasCitations
    ? (sources as SourceCitation[]).some((s) => s.citation_verified === true)
    : false;

  const label = resolveFieldLabel(item);
  const value = resolveFieldValue(item, valueAsSubtext);

  // Best source text for feedback context.
  const sourceTextContext =
    (sources as SourceCitation[] | undefined)?.[0]?.source_text ?? "";

  function handleDirectJump() {
    if (!canJump) return;
    const targets = allTargets.length
      ? allTargets
      : primaryTarget
        ? [primaryTarget]
        : [];
    if (!targets.length) return;
    jumpToCitations(targets);
    setOpen(true);
  }

  async function sendFeedback(
    rating: "up" | "down",
    extra?: { issue_type: string; correct_value: string; comment: string }
  ) {
    if (!documentId || !extractionType) return;
    setSubmitted(rating);
    try {
      await submitFieldFeedback(documentId, {
        field_key: item.field_key ?? label.toLowerCase().replace(/\s+/g, "_"),
        extraction_type: extractionType,
        rating,
        extracted_value: value,
        source_text_context: sourceTextContext,
        ...(extra ?? {}),
      });
    } catch {
      // non-blocking — feedback failure shouldn't disrupt the user
    }
  }

  async function handleCorrectionSubmit(data: {
    issue_type: string;
    correct_value: string;
    comment: string;
  }) {
    await sendFeedback("down", data);
    setFeedbackState("done");
  }

  return (
    <div className="w-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-ink">
            <span className="font-semibold">{label}:</span>{" "}
            <span className="font-normal">{value || "—"}</span>
          </p>

          {/* Scope-of-work partial-content notice */}
          {item.field_key === "project_description" &&
            ((item._scope_chunk_count ?? 0) > 1 || item._scope_truncated) && (
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-amber-700">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 16 16"
                  fill="currentColor"
                  className="h-3 w-3 shrink-0"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M6.701 2.25c.577-1 2.02-1 2.598 0l5.196 9a1.5 1.5 0 0 1-1.299 2.25H2.804a1.5 1.5 0 0 1-1.3-2.25l5.197-9ZM8 5a.75.75 0 0 1 .75.75v2.5a.75.75 0 0 1-1.5 0v-2.5A.75.75 0 0 1 8 5Zm0 6a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
                    clipRule="evenodd"
                  />
                </svg>
                <span>
                  {item._scope_truncated
                    ? "Content was clipped — scope exceeds display limit."
                    : `Scope spans ${item._scope_chunk_count} document section(s) — may not be complete.`}
                </span>
                {primaryTarget && canJump && (
                  <button
                    type="button"
                    onClick={handleDirectJump}
                    className="inline-flex items-center gap-0.5 font-medium underline underline-offset-2 hover:text-amber-900"
                  >
                    View in document
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 12 12"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="h-2.5 w-2.5"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2 6h8m-3-3 3 3-3 3" />
                    </svg>
                  </button>
                )}
              </p>
            )}

          {/* Correction form */}
          {feedbackState === "form" && (
            <CorrectionForm
              fieldLabel={label}
              extractedValue={value}
              onSubmit={handleCorrectionSubmit}
              onDismiss={() => { setFeedbackState("idle"); setSubmitted(null); }}
            />
          )}

          {feedbackState === "done" && submitted === "down" && (
            <p className="mt-1 text-[10px] font-medium text-red-600">
              Feedback saved — thanks!
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <CopyValueButton value={value || "—"} />
          {hasCitations && hasVerified && primaryTarget && canJump && (
            <JumpButton onClick={handleDirectJump} />
          )}
          {hasCitations && !hasVerified && <UnverifiedBadge />}
          {extractionType && feedbackState !== "form" && (
            <FeedbackButtons
              onUp={() => { sendFeedback("up"); setFeedbackState("done"); }}
              onDown={() => setFeedbackState("form")}
              submitted={submitted}
            />
          )}
          {hasCitations && (
            <CitationToggle
              open={open}
              count={sources!.length}
              onToggle={() => setOpen((v) => !v)}
            />
          )}
        </div>

        {confidenceBadge}
      </div>

      {open && hasCitations && (
        <CitationPanel sources={sources as SourceCitation[]} />
      )}
    </div>
  );
}
