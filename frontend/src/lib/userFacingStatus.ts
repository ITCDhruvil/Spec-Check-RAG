import type { PipelineStage } from "@/lib/types/document";
import type { SummaryStatus } from "@/lib/types/intelligence";

const PARSING_STAGES: PipelineStage[] = [
  "uploaded",
  "queued",
  "intake_processing",
  "intake_completed",
  "parsing_processing",
  "parsing_completed",
  "ocr_processing",
  "ocr_completed",
  "sectioning_processing",
  "sectioning_completed",
];

const ANALYSIS_STAGES: PipelineStage[] = [
  "chunking_processing",
  "chunking_completed",
  "embedding_processing",
  "embedding_completed",
  "extraction_processing",
  "extraction_completed",
  "summary_processing",
];

/** Short label for tables and badges */
export function userFacingDocumentLabel(status: PipelineStage): string {
  if (status === "failed") return "Failed";
  if (status === "completed") return "Ready";
  if (PARSING_STAGES.includes(status)) return "Reading document";
  if (ANALYSIS_STAGES.includes(status)) return "Analyzing";
  return "Processing";
}

export type UserProcessingPhase =
  | "uploading"
  | "reading"
  | "analyzing"
  | "ready"
  | "failed";

export function resolveUserProcessingPhase(
  documentStatus: string | undefined,
  summaryStatus: SummaryStatus | null | undefined,
  options?: {
    uploadInProgress?: boolean;
    summaryStarting?: boolean;
    /** True when queued/uploaded with no worker progress */
    waitingToStart?: boolean;
  }
): UserProcessingPhase {
  if (options?.uploadInProgress) return "uploading";
  if (documentStatus === "failed" || summaryStatus === "failed") return "failed";
  if (summaryStatus === "completed" && documentStatus === "completed") return "ready";

  if (
    summaryStatus === "processing" ||
    options?.summaryStarting ||
    (documentStatus === "completed" &&
      summaryStatus !== "completed" &&
      summaryStatus != null)
  ) {
    return "analyzing";
  }

  if (
    documentStatus === "queued" ||
    documentStatus === "uploaded" ||
    options?.waitingToStart
  ) {
    return "reading";
  }

  if (
    !documentStatus ||
    PARSING_STAGES.includes(documentStatus as PipelineStage) ||
    (documentStatus !== "completed" && documentStatus !== "failed")
  ) {
    return "reading";
  }

  if (documentStatus === "completed" && !summaryStatus) {
    return "analyzing";
  }

  return "reading";
}

const PHASE_COPY: Record<
  UserProcessingPhase,
  { title: string; description: string }
> = {
  uploading: {
    title: "Uploading your document",
    description: "Please keep this page open until the upload finishes.",
  },
  reading: {
    title: "Reading your document",
    description:
      "We are extracting text and structure from the PDF. Large tenders (40+ pages) can take 2–5 minutes.",
  },
  analyzing: {
    title: "Preparing your specification briefing",
    description:
      "We are analyzing requirements, deadlines, and risks. This step often takes 5–15 minutes for large documents.",
  },
  ready: {
    title: "Your briefing is ready",
    description: "Scroll down to review the summary and key insights.",
  },
  failed: {
    title: "Something went wrong",
    description: "We could not finish processing this document. Try uploading again or contact support.",
  },
};

export function userProcessingCopy(phase: UserProcessingPhase) {
  return PHASE_COPY[phase];
}
