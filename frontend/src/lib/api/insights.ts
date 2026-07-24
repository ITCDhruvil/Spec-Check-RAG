import { apiClient } from "@/lib/api/client";

export type UserInsightRow = {
  user_id: string;
  username: string;
  email: string;
  docs_total: number;
  docs_completed: number;
  docs_failed: number;
  fields_extracted: number;
  fields_corrected: number;
  fields_confirmed: number;
  correction_rate: number;
  avg_processing_seconds: number | null;
  retry_jobs: number;
  last_activity: string | null;
};

export type UserInsightsResponse = {
  period_days: number;
  users: UserInsightRow[];
  accuracy_trend: {
    date: string;
    feedback_total: number;
    corrections: number;
    correction_rate: number;
  }[];
  field_problem_ranking: { field_key: string; corrections: number }[];
  failure_stats: {
    documents_failed: number;
    documents_total: number;
    top_error_codes: { error_code: string; count: number }[];
  };
  activity_timeline: { date: string; uploads: number; completed: number }[];
};

export type UserInsightDetail = {
  user_id: string;
  period_days: number;
  documents: {
    id: string;
    filename: string;
    status: string;
    size_mb: number;
    created_at: string;
  }[];
  fields: { field: string; count: number }[];
  corrected: { field: string; count: number }[];
  corrected_by_document: {
    document_id: string;
    filename: string;
    fields: { field: string; count: number }[];
  }[];
};

export async function fetchUserInsights(days = 30): Promise<UserInsightsResponse> {
  const { data } = await apiClient.get<UserInsightsResponse>(
    "/analytics/user-insights/",
    { params: { days } }
  );
  return data;
}

export async function fetchUserInsightDetail(
  userId: string,
  days = 30
): Promise<UserInsightDetail> {
  const { data } = await apiClient.get<UserInsightDetail>(
    `/analytics/user-insights/${userId}/`,
    { params: { days } }
  );
  return data;
}

export type ExportCell = { status: string; correction: string; reason: string };

export type ExportPreview = {
  period_days: number;
  scope_user_id: string | null;
  summary: { metric: string; value: string }[];
  per_user: UserInsightRow[];
  documents: {
    columns: {
      id: string;
      filename: string;
      uploaded_by: string;
      status: string;
      uploaded: string;
    }[];
    rows: { field_key: string; label: string; cells: ExportCell[] }[];
  };
};

export type AIInsight = {
  title: string;
  detail: string;
  kind: "problem" | "recommendation" | "pattern";
};

export async function fetchAIInsights(
  days = 30,
  refresh = false
): Promise<{ period_days: number; insights: AIInsight[] }> {
  const { data } = await apiClient.get("/analytics/ai-insights/", {
    params: { days, ...(refresh ? { refresh: 1 } : {}) },
    timeout: 0, // first call per data snapshot runs an LLM analysis
  });
  return data;
}

export async function fetchExportPreview(
  days = 30,
  userId?: string
): Promise<ExportPreview> {
  const { data } = await apiClient.get<ExportPreview>("/analytics/export/preview/", {
    params: { days, ...(userId ? { user_id: userId } : {}) },
  });
  return data;
}

/** Download the analytics Excel workbook and trigger a browser save. */
export async function downloadAnalyticsExport(days = 30, userId?: string): Promise<void> {
  const { data, headers } = await apiClient.get<ArrayBuffer>("/analytics/export/", {
    params: { days, ...(userId ? { user_id: userId } : {}) },
    responseType: "arraybuffer",
    timeout: 0,
  });
  const blob = new Blob([data], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const disposition = String(headers["content-disposition"] ?? "");
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? "spec-check-analytics.xlsx";

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
