import { apiClient } from "@/lib/api/client";
import type {
  DocumentDetail,
  DocumentListItem,
  DocumentStatusResponse,
  DocumentUploadResponse,
  DocumentVersionType,
  PaginatedResponse,
  TenderSummary,
} from "@/lib/types/document";

export interface UploadDocumentParams {
  file: File;
  tenderReference?: string;
  tenderId?: string;
  tenderTitle?: string;
  organization?: string;
  versionType?: DocumentVersionType;
  versionLabel?: string;
  supersedesVersionId?: string;
  versionNotes?: string;
  onProgress?: (percent: number) => void;
}

export async function uploadDocument({
  file,
  tenderReference,
  tenderId,
  tenderTitle,
  organization,
  versionType,
  versionLabel,
  supersedesVersionId,
  versionNotes,
  onProgress,
}: UploadDocumentParams): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (tenderReference) formData.append("tender_reference", tenderReference);
  if (tenderId) formData.append("tender_id", tenderId);
  if (tenderTitle) formData.append("tender_title", tenderTitle);
  if (organization) formData.append("organization", organization);
  if (versionType) formData.append("version_type", versionType);
  if (versionLabel) formData.append("version_label", versionLabel);
  if (supersedesVersionId) formData.append("supersedes_version_id", supersedesVersionId);
  if (versionNotes) formData.append("version_notes", versionNotes);

  const { data } = await apiClient.post<DocumentUploadResponse>(
    "/documents/upload/",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event) => {
        if (!event.total || !onProgress) return;
        onProgress(Math.round((event.loaded * 100) / event.total));
      },
    }
  );
  return data;
}

export async function listDocuments(
  page = 1
): Promise<PaginatedResponse<DocumentListItem>> {
  const { data } = await apiClient.get<PaginatedResponse<DocumentListItem>>(
    "/documents/",
    { params: { page } }
  );
  return data;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const { data } = await apiClient.get<DocumentDetail>(`/documents/${id}/`);
  return data;
}

/** Fetch document bytes with auth (for PDF.js — cannot send headers on raw URL). */
export async function fetchDocumentFile(
  id: string,
  variant: "file" | "preview-pdf" = "file"
): Promise<ArrayBuffer> {
  const path =
    variant === "preview-pdf"
      ? `/documents/${id}/preview-pdf/`
      : `/documents/${id}/file/`;
  const { data } = await apiClient.get<ArrayBuffer>(path, {
    responseType: "arraybuffer",
  });
  return data;
}

/** URL for streaming the original uploaded file (PDF preview, download). */
export function getDocumentFileUrl(id: string): string {
  const baseURL =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
  return `${baseURL}/documents/${id}/file/`;
}

/** URL for the layout-faithful PDF preview generated from DOCX. */
export function getDocumentPreviewPdfUrl(id: string): string {
  const baseURL =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
  return `${baseURL}/documents/${id}/preview-pdf/`;
}

export async function getDocumentStatus(
  id: string
): Promise<DocumentStatusResponse> {
  const { data } = await apiClient.get<DocumentStatusResponse>(
    `/documents/${id}/status/`
  );
  return data;
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient.delete(`/documents/${id}/`);
}

/** Start parse pipeline when upload is stuck in queued (dev / no Celery). */
export async function kickDocumentProcessing(id: string): Promise<void> {
  await apiClient.post(`/documents/${id}/process/`);
}

export async function listTenders(
  page = 1
): Promise<PaginatedResponse<TenderSummary>> {
  const { data } = await apiClient.get<PaginatedResponse<TenderSummary>>(
    "/tenders/",
    { params: { page } }
  );
  return data;
}

export async function checkHealth(): Promise<{
  status: string;
  checks: Record<string, { status: string }>;
}> {
  const axios = (await import("axios")).default;
  const healthUrl =
    process.env.NEXT_PUBLIC_API_HEALTH_URL ??
    "http://localhost:8000/api/health/";
  const { data } = await axios.get(healthUrl);
  return data;
}
