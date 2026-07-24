"use client";

import { CheckIcon } from "@/components/ui/icons";
import type { PipelineStage } from "@/lib/types/document";

const PIPELINE_STEPS: { id: string; label: string; stages: PipelineStage[] }[] = [
  {
    id: "chunking",
    label: "Chunking",
    stages: ["chunking_processing", "chunking_completed"],
  },
  {
    id: "embedding",
    label: "Embedding",
    stages: ["embedding_processing", "embedding_completed"],
  },
  {
    id: "extraction",
    label: "Extraction",
    stages: ["extraction_processing", "extraction_completed"],
  },
  {
    id: "summary",
    label: "Summary",
    stages: ["summary_processing", "completed"],
  },
];

function stageIndex(stage: string | null | undefined): number {
  if (!stage) return -1;
  for (let i = 0; i < PIPELINE_STEPS.length; i++) {
    const step = PIPELINE_STEPS[i];
    if (step.stages.includes(stage as PipelineStage)) {
      const sub = step.stages.indexOf(stage as PipelineStage);
      return i + (sub >= 0 ? (sub + 1) / step.stages.length : 0) * 0.25;
    }
  }
  if (stage === "processing" || stage.includes("processing")) {
    return 0.5;
  }
  return -1;
}

function percentFromStage(stage: string | null | undefined): number {
  const idx = stageIndex(stage);
  if (idx < 0) return 0;
  return Math.min(100, Math.round((idx / PIPELINE_STEPS.length) * 100));
}

export function PipelineProgressBar({
  progressStage,
  indeterminate = false,
}: {
  progressStage?: string | null;
  /** True while HTTP request is in-flight (sync mode — no status polls yet) */
  indeterminate?: boolean;
}) {
  const percent = indeterminate ? undefined : percentFromStage(progressStage ?? null);
  const activeStepIndex = indeterminate
    ? -1
    : Math.floor((percent ?? 0) / (100 / PIPELINE_STEPS.length));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-ink-muted">
        <span>Pipeline progress</span>
        <span className="font-medium text-ink">
          {indeterminate
            ? "Starting…"
            : percent !== undefined
              ? `${percent}%`
              : progressStage
                ? progressStage.replace(/_/g, " ")
                : "—"}
        </span>
      </div>

      <div
        className="h-2.5 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Summary generation progress"
      >
        {indeterminate ? (
          <div className="h-full w-1/3 animate-pulse rounded-full bg-accent" />
        ) : (
          <div
            className="h-full rounded-full bg-accent transition-all duration-500 ease-out"
            style={{ width: `${percent ?? 0}%` }}
          />
        )}
      </div>

      <div className="grid grid-cols-4 gap-2">
        {PIPELINE_STEPS.map((step, i) => {
          const isDone = !indeterminate && i < activeStepIndex;
          const isActive =
            indeterminate && i === 0
              ? true
              : !indeterminate && i === activeStepIndex;
          const isPending = !indeterminate && i > activeStepIndex;

          return (
            <div key={step.id} className="text-center">
              <div
                className={`mx-auto mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                  isDone
                    ? "bg-accent text-white"
                    : isActive
                      ? "bg-accent/20 text-accent ring-2 ring-accent"
                      : isPending
                        ? "bg-surface-muted text-ink-muted"
                        : "bg-surface-muted text-ink-muted"
                }`}
              >
                {isDone ? <CheckIcon className="h-3.5 w-3.5" /> : i + 1}
              </div>
              <p
                className={`text-xs ${
                  isActive ? "font-medium text-ink" : "text-ink-muted"
                }`}
              >
                {step.label}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
