import { apiClient } from "@/lib/api/client";
import type {
  ExtractedInsight,
  GenerateSummaryResponse,
  GeneratedSummary,
  SummaryStatusResponse,
} from "@/lib/types/intelligence";

/** Sync regeneration can take several minutes */
const INTELLIGENCE_TIMEOUT_MS = 600000;

export async function generateSummary(
  documentId: string
): Promise<GenerateSummaryResponse> {
  const { data } = await apiClient.post<GenerateSummaryResponse>(
    `/documents/${documentId}/summary/generate/`,
    {},
    { timeout: INTELLIGENCE_TIMEOUT_MS }
  );
  return data;
}

export async function regenerateSummary(
  documentId: string
): Promise<GenerateSummaryResponse> {
  const { data } = await apiClient.post<GenerateSummaryResponse>(
    `/documents/${documentId}/summary/regenerate/`,
    {},
    { timeout: INTELLIGENCE_TIMEOUT_MS }
  );
  return data;
}

export async function getSummary(documentId: string): Promise<GeneratedSummary> {
  const { data } = await apiClient.get<GeneratedSummary>(
    `/documents/${documentId}/summary/`
  );
  return data;
}

export async function getSummaryStatus(
  documentId: string
): Promise<SummaryStatusResponse> {
  const { data } = await apiClient.get<SummaryStatusResponse>(
    `/documents/${documentId}/summary/status/`
  );
  return data;
}

export async function cancelSummary(
  documentId: string
): Promise<{ message: string; summary_id?: string }> {
  const { data } = await apiClient.post(
    `/documents/${documentId}/summary/cancel/`,
    {}
  );
  return data;
}

export async function repairSpecCheck(documentId: string): Promise<{
  message: string;
  summary_id: string;
  fields_populated: Record<string, number>;
}> {
  const { data } = await apiClient.post(
    `/documents/${documentId}/summary/repair-spec-check/`,
    {}
  );
  return data;
}

export async function listInsights(
  documentId: string
): Promise<ExtractedInsight[]> {
  const { data } = await apiClient.get<ExtractedInsight[]>(
    `/documents/${documentId}/insights/`
  );
  return data;
}

export interface FieldFeedbackPayload {
  field_key: string;
  extraction_type: string;
  rating: "up" | "down";
  issue_type?: string;
  extracted_value?: string;
  correct_value?: string;
  comment?: string;
  source_text_context?: string;
  doc_type?: string;
}

export async function submitFieldFeedback(
  documentId: string,
  payload: FieldFeedbackPayload
): Promise<{ id: string; rating: string; field_key: string }> {
  const { data } = await apiClient.post(
    `/documents/${documentId}/field-feedback/`,
    payload
  );
  return data;
}

export interface HealthStatus {
  status: "healthy" | "degraded" | "maintenance";
  maintenance: boolean;
  reason?: string;
  expected_end?: string;
}

export async function getHealthStatus(): Promise<HealthStatus> {
  const { data } = await apiClient.get<HealthStatus>("/health/", {
    baseURL: process.env.NEXT_PUBLIC_API_HEALTH_URL?.replace("/health/", "") ?? undefined,
  });
  return data;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function briefingPdfDownloadUrl(
  documentId: string,
  variant: "full" | "executive" = "full"
): string {
  const params = new URLSearchParams({ variant });
  return `${API_BASE}/documents/${documentId}/summary/download/?${params}`;
}

/** Trigger browser download of the structured briefing PDF. */
export async function downloadBriefingPdf(
  documentId: string,
  originalFilename: string,
  variant: "full" | "executive" = "full"
): Promise<void> {
  const url = briefingPdfDownloadUrl(documentId, variant);
  const response = await fetch(url);
  if (!response.ok) {
    let message = "Failed to download briefing PDF";
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const stem = originalFilename.replace(/\.[^.]+$/, "") || "document";
  const suffix =
    variant === "executive" ? "executive_summary" : "briefing";
  const fallbackName = `${stem}_procurement_${suffix}.pdf`;
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";\n]+)"?/i.exec(disposition);
  const filename = match?.[1]?.trim() || fallbackName;

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

// ---------------------------------------------------------------------------
// Feedback Insights admin API
// ---------------------------------------------------------------------------

export interface FeedbackTypeBreakdown {
  extraction_type: string;
  total: number;
  up: number;
  down: number;
  with_correction: number;
  used_in_finetune: number;
}

export interface FeedbackStats {
  total: number;
  up: number;
  down: number;
  with_correction: number;
  used_in_finetune: number;
  by_type: FeedbackTypeBreakdown[];
  active_jobs: FineTuneJobRow[];
  fine_tuned_models: Record<string, string>;
  settings: {
    finetune_enabled: boolean;
    threshold: number;
    max_cost_usd: number;
  };
}

export interface FeedbackRow {
  id: string;
  document_id: string;
  document_filename: string;
  field_key: string;
  extraction_type: string;
  doc_type: string;
  rating: "up" | "down";
  issue_type: string;
  extracted_value: string;
  correct_value: string;
  comment: string;
  source_text_context: string;
  used_in_finetune: boolean;
  created_at: string;
}

export interface FeedbackListResponse {
  count: number;
  page: number;
  page_size: number;
  results: FeedbackRow[];
}

export interface FineTuneJobRow {
  id: string;
  extraction_type: string;
  status: string;
  azure_job_id: string;
  base_model: string;
  fine_tuned_model_id: string;
  feedback_count: number;
  estimated_cost_usd: number;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface AppSettings {
  FINETUNE_ENABLED: boolean;
  FINETUNE_FEEDBACK_THRESHOLD: number;
  FINETUNE_MAX_COST_USD: number;
  FINETUNE_BASE_MODEL: string;
}

export async function getFeedbackStats(): Promise<FeedbackStats> {
  const { data } = await apiClient.get<FeedbackStats>("/feedback/stats/");
  return data;
}

export async function getFeedbackList(params?: {
  extraction_type?: string;
  rating?: string;
  used_in_finetune?: string;
  page?: number;
  page_size?: number;
}): Promise<FeedbackListResponse> {
  const { data } = await apiClient.get<FeedbackListResponse>("/feedback/", { params });
  return data;
}

export async function deleteFeedback(id: string): Promise<void> {
  await apiClient.delete(`/feedback/${id}/`);
}

export async function getFineTuneJobs(): Promise<{ results: FineTuneJobRow[] }> {
  const { data } = await apiClient.get<{ results: FineTuneJobRow[] }>("/finetune/jobs/");
  return data;
}

export async function triggerFineTune(extraction_type: string): Promise<{
  job_id: string;
  status: string;
  feedback_count: number;
  estimated_cost_usd: number;
}> {
  const { data } = await apiClient.post("/finetune/trigger/", { extraction_type });
  return data;
}

export async function getAppSettings(): Promise<AppSettings> {
  const { data } = await apiClient.get<AppSettings>("/feedback/settings/");
  return data;
}

export async function updateAppSettings(
  settings: Partial<AppSettings>
): Promise<{ updated: Partial<AppSettings>; errors?: Record<string, string> }> {
  const { data } = await apiClient.patch("/feedback/settings/", settings);
  return data;
}
