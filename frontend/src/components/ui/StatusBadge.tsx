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
  neutral: "bg-slate-100 text-slate-700",
  pending: "bg-amber-50 text-amber-800",
  active: "bg-blue-50 text-blue-800",
  success: "bg-emerald-50 text-emerald-800",
  error: "bg-red-50 text-red-800",
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
