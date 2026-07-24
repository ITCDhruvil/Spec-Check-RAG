import { userFacingDocumentLabel } from "@/lib/userFacingStatus";
import type { PipelineStage } from "@/lib/types/document";

type BadgeTone = "neutral" | "pending" | "active" | "success" | "error";

function toneForStage(status: PipelineStage): BadgeTone {
  if (status === "failed") return "error";
  if (status === "completed") return "success";
  if (status === "queued" || status === "uploaded") return "pending";
  return "active";
}

const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-ink-muted",
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  active: "bg-accent/10 text-accent",
  success: "bg-green-100 text-green-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  error: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
};

export function StatusBadge({ status }: { status: PipelineStage }) {
  const tone = toneForStage(status);
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]}`}
    >
      {userFacingDocumentLabel(status)}
    </span>
  );
}
