"use client";

import { useEffect, useRef, useState } from "react";

import {
  resolveUserProcessingPhase,
  type UserProcessingPhase,
} from "@/lib/userFacingStatus";
import type { SummaryStatus } from "@/lib/types/intelligence";

// ─── Stage → human-readable label ────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  uploaded:               "Document uploaded, waiting to start…",
  queued:                 "Queued for processing…",
  intake_processing:      "Starting document processing…",
  intake_completed:       "Document ready for parsing",
  parsing_processing:     "Reading and parsing the document…",
  parsing_completed:      "Document parsed successfully",
  ocr_processing:         "Running OCR on scanned pages…",
  ocr_completed:          "OCR scan complete",
  sectioning_processing:  "Identifying document sections…",
  sectioning_completed:   "Document structure mapped",
  chunking_processing:    "Preparing document for AI analysis…",
  chunking_completed:     "Document chunked for analysis",
  embedding_processing:   "Creating semantic index…",
  embedding_completed:    "Semantic index ready",
  extraction_processing:  "Extracting specification data with AI…",
  extraction_completed:   "Extraction complete, generating briefing…",
  summary_processing:     "Generating your final briefing…",
  completed:              "Your briefing is ready",
  failed:                 "Processing failed",
};

/** Backend uses document status "completed" when *parsing* finishes, not the briefing. */
const PARSING_DONE_STATUS = "completed";

const INTELLIGENCE_STAGES = new Set([
  "chunking_processing",
  "chunking_completed",
  "embedding_processing",
  "embedding_completed",
  "extraction_processing",
  "extraction_completed",
  "summary_processing",
]);

/**
 * Single stage key for labels + percent. Never returns "completed" unless the
 * briefing is actually ready (phase === "ready").
 */
function resolveDisplayStage(
  phase: UserProcessingPhase,
  progressStage?: string | null,
  documentStatus?: string,
  summaryStatus?: SummaryStatus | null,
  summaryStarting?: boolean,
): string {
  if (phase === "ready") return "completed";
  if (phase === "failed") return "failed";

  const raw = progressStage ?? documentStatus ?? "";

  if (INTELLIGENCE_STAGES.has(raw)) return raw;

  if (raw === PARSING_DONE_STATUS || documentStatus === PARSING_DONE_STATUS) {
    if (summaryStatus === "processing" || summaryStarting) {
      return "chunking_processing";
    }
    return "parsing_completed";
  }

  if (raw && STAGE_LABELS[raw]) return raw;
  if (phase === "analyzing") return "chunking_processing";
  if (phase === "reading") return documentStatus ?? "parsing_processing";
  return "queued";
}

function getStageLabel(displayStage: string): string {
  if (STAGE_LABELS[displayStage]) return STAGE_LABELS[displayStage];
  return "Processing your document…";
}

// ─── Stage → progress percentage ─────────────────────────────────────────────

const STAGE_PERCENT: Record<string, number> = {
  uploaded:               3,
  queued:                 5,
  intake_processing:      8,
  intake_completed:       12,
  parsing_processing:     16,
  parsing_completed:      22,
  ocr_processing:         19,
  ocr_completed:          23,
  sectioning_processing:  26,
  sectioning_completed:   30,
  chunking_processing:    34,
  chunking_completed:     42,
  embedding_processing:   46,
  embedding_completed:    52,
  extraction_processing:  56,
  extraction_completed:   85,
  summary_processing:     90,
  completed:              100,
  failed:                 0,
};

function stageToPercent(
  phase: UserProcessingPhase,
  displayStage: string,
): number {
  if (phase === "ready") return 100;
  if (phase === "failed") return 0;
  if (phase === "uploading") return 3;
  if (STAGE_PERCENT[displayStage] !== undefined) {
    return STAGE_PERCENT[displayStage];
  }
  return phase === "reading" ? 10 : 34;
}

/** Progress bar only moves forward during a run (no 100% → 56% jumps). */
function useMonotonicPercent(target: number, isActive: boolean, isDone: boolean) {
  const maxRef = useRef(0);
  const wasActiveRef = useRef(false);

  useEffect(() => {
    if (isActive && !wasActiveRef.current) {
      maxRef.current = 0;
    }
    wasActiveRef.current = isActive;
  }, [isActive]);

  if (isDone) return 100;
  if (!isActive) return target;
  maxRef.current = Math.max(maxRef.current, target);
  return maxRef.current;
}

// ─── Hooks ────────────────────────────────────────────────────────────────────

function useProcessingTimer(active: boolean, done: boolean) {
  const startedAtRef = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [finalElapsed, setFinalElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (active && startedAtRef.current === null) {
      startedAtRef.current = Date.now();
      setElapsed(0);
      setFinalElapsed(null);
    }
  }, [active]);

  useEffect(() => {
    if (!active || startedAtRef.current === null) return;
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAtRef.current!) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [active]);

  useEffect(() => {
    if (done && startedAtRef.current !== null && finalElapsed === null) {
      setFinalElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }
  }, [done, finalElapsed]);

  return {
    visible: startedAtRef.current !== null,
    seconds: finalElapsed ?? elapsed,
    isDone: finalElapsed !== null,
  };
}

function useLiveStatusText(displayStage: string) {
  const initialLabel = getStageLabel(displayStage);
  const [displayText, setDisplayText] = useState(initialLabel);
  const [visible, setVisible] = useState(true);
  const prevStageRef = useRef(displayStage);

  useEffect(() => {
    if (displayStage === prevStageRef.current) return;
    prevStageRef.current = displayStage;

    const nextText = getStageLabel(displayStage);
    if (nextText === displayText) return;

    setVisible(false);
    const t = setTimeout(() => {
      setDisplayText(nextText);
      setVisible(true);
    }, 260);
    return () => clearTimeout(t);
  }, [displayStage, displayText]);

  return { text: displayText, visible };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatElapsed(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ─── Stop confirmation modal ──────────────────────────────────────────────────

function StopModal({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-labelledby="stop-modal-title"
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-surface-border bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Icon */}
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
          <svg
            className="h-6 w-6 text-red-600"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden
          >
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        </div>

        <h3
          id="stop-modal-title"
          className="text-base font-semibold text-gray-900"
        >
          Stop processing?
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-gray-500">
          All progress will be discarded. You can restart processing from the
          beginning at any time.
        </p>

        {/* Actions */}
        <div className="mt-6 flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
          >
            Keep going
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm();
            }}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Yes, stop it
          </button>
        </div>
      </div>
    </div>
  );
}

function StopButton({ onStop }: { onStop: () => void }) {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-700"
      >
        <svg
          className="h-3.5 w-3.5"
          viewBox="0 0 14 14"
          fill="none"
          aria-hidden
        >
          <rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor" />
        </svg>
        Stop processing
      </button>

      {modalOpen && (
        <StopModal
          onConfirm={() => {
            setModalOpen(false);
            onStop();
          }}
          onCancel={() => setModalOpen(false)}
        />
      )}
    </>
  );
}

// ─── Failed state cards ───────────────────────────────────────────────────────

function CancelledCard() {
  return (
    <div className="rounded-lg border border-surface-border bg-surface p-6">
      <div className="flex items-start gap-4">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-muted">
          <svg
            className="h-4 w-4 text-ink-muted"
            viewBox="0 0 16 16"
            fill="currentColor"
            aria-hidden
          >
            <rect x="4" y="4" width="8" height="8" rx="1.5" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold text-ink">
            Processing stopped
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            You stopped processing this document. No data was saved. You can
            restart from the beginning below.
          </p>
        </div>
      </div>
    </div>
  );
}

function ErrorCard() {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6">
      <div className="flex items-start gap-4">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-100 text-sm font-bold text-red-600">
          !
        </div>
        <div>
          <p className="text-sm font-semibold text-red-900">
            Something went wrong
          </p>
          <p className="mt-1 text-sm text-red-700">
            We could not finish processing this document. You can try again
            below.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function SimpleProcessingCard({
  documentStatus,
  summaryStatus,
  uploadInProgress,
  summaryStarting,
  waitingToStart,
  progressStage,
  errorMessage,
  onStop,
}: {
  documentStatus?: string;
  summaryStatus?: SummaryStatus | null;
  uploadInProgress?: boolean;
  summaryStarting?: boolean;
  waitingToStart?: boolean;
  progressStage?: string | null;
  errorMessage?: string | null;
  onStop?: () => void;
}) {
  const phase = resolveUserProcessingPhase(documentStatus, summaryStatus, {
    uploadInProgress,
    summaryStarting,
    waitingToStart,
  });

  const isActive = phase !== "ready" && phase !== "failed";
  const isDone = phase === "ready";

  const displayStage = resolveDisplayStage(
    phase,
    progressStage,
    documentStatus,
    summaryStatus,
    summaryStarting,
  );

  const timer = useProcessingTimer(
    phase !== "uploading" && isActive,
    isDone,
  );
  const { text: statusText, visible: textVisible } = useLiveStatusText(displayStage);

  const rawPercent = stageToPercent(phase, displayStage);
  const percent = useMonotonicPercent(rawPercent, isActive, isDone);
  const isIndeterminate =
    (documentStatus === "queued" || documentStatus === "uploaded") &&
    !progressStage &&
    !waitingToStart;

  if (phase === "failed") {
    const wasCancelled = errorMessage?.toLowerCase().includes("cancel");
    return wasCancelled ? <CancelledCard /> : <ErrorCard />;
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface p-6">
      {/* ── Header row: status dot + live status text + timer ── */}
      <div className="flex items-center gap-3">
        {/* Pulsing status dot */}
        <span
          className="relative flex h-2.5 w-2.5 shrink-0"
          aria-hidden
        >
          {!isDone && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
          )}
          <span
            className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
              isDone ? "bg-emerald-500" : "bg-accent"
            }`}
          />
        </span>

        {/* Live stage status */}
        <p
          className={`flex-1 text-sm font-medium text-ink transition-opacity duration-300 ${
            textVisible ? "opacity-100" : "opacity-0"
          }`}
          aria-live="polite"
          aria-atomic="true"
        >
          {statusText}
        </p>

        {/* Elapsed timer */}
        {timer.visible && (
          <span
            className={`shrink-0 font-mono text-sm tabular-nums ${
              timer.isDone ? "font-medium text-emerald-700" : "text-ink-muted"
            }`}
            aria-label={
              timer.isDone
                ? `Done in ${formatElapsed(timer.seconds)}`
                : `Elapsed: ${formatElapsed(timer.seconds)}`
            }
          >
            {timer.isDone
              ? `Done in ${formatElapsed(timer.seconds)}`
              : formatElapsed(timer.seconds)}
          </span>
        )}
      </div>

      {/* ── Progress bar ── */}
      <div className="mt-5">
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          {isIndeterminate ? (
            <div className="h-full w-2/5 animate-pulse rounded-full bg-accent/60" />
          ) : (
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                isDone ? "bg-emerald-500" : "bg-accent"
              }`}
              style={{ width: `${percent}%` }}
            />
          )}
        </div>
        {!isIndeterminate && (
          <p className="mt-1.5 text-right text-xs tabular-nums text-ink-muted">
            {percent}%
          </p>
        )}
      </div>

      {/* ── Stop button ── */}
      {onStop && isActive && (
        <div className="mt-5 flex justify-end">
          <StopButton onStop={onStop} />
        </div>
      )}
    </div>
  );
}
