/** Granular pipeline stages — must match backend PipelineStage */
export type PipelineStage =
  | "uploaded"
  | "queued"
  | "intake_processing"
  | "intake_completed"
  | "parsing_processing"
  | "parsing_completed"
  | "ocr_processing"
  | "ocr_completed"
  | "sectioning_processing"
  | "sectioning_completed"
  | "chunking_processing"
  | "chunking_completed"
  | "embedding_processing"
  | "embedding_completed"
  | "extraction_processing"
  | "extraction_completed"
  | "summary_processing"
  | "completed"
  | "failed";

/** @deprecated Use PipelineStage */
export type ProcessingStatus = PipelineStage;

export const TERMINAL_STAGES: PipelineStage[] = ["completed", "failed"];

export const ACTIVE_STAGES: PipelineStage[] = [
  "intake_processing",
  "parsing_processing",
  "ocr_processing",
  "sectioning_processing",
  "chunking_processing",
  "embedding_processing",
  "extraction_processing",
  "summary_processing",
];

export interface StructuredProcessingError {
  error_type: string;
  stage: string;
  recoverable: boolean;
  retry_count: number;
  message: string;
  details?: Record<string, unknown>;
}

export interface ProcessingJob {
  id: string;
  status: PipelineStage;
  current_stage: PipelineStage;
  pipeline_stage: PipelineStage;
  completed_stages: string[];
  retry_count: number;
  error_code: string;
  error_message: string;
  last_error: StructuredProcessingError | Record<string, never>;
  celery_task_id: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TenderSummary {
  id: string;
  reference_code: string;
  title: string;
  organization: string;
  status: string;
  version_count: number;
  current_version: DocumentVersionSummary | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersionSummary {
  id: string;
  document_id: string;
  version_type: string;
  version_label: string;
  version_sequence: number;
  is_current: boolean;
  supersedes_id: string | null;
  published_at: string | null;
  created_at: string;
}

export interface ExtractedContentSummary {
  content_ready: boolean;
  raw_text_length: number;
  page_count: number;
  section_count: number;
  pipeline_version?: string;
}

export interface SourceTraceSchema {
  source_document: string;
  document_id: string;
  tender_reference: string | null;
  version_label: string | null;
  page: number | null;
  section: string | null;
  section_path: string | null;
  chunk_id: string | null;
  confidence: number | null;
}

export interface DocumentListItem {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: PipelineStage;
  /** User finished pulling data — opens in Manual view from the dashboard. */
  marked_done?: boolean;
  tender_reference: string | null;
  /** User-given tender title — preferred display name over the raw filename. */
  tender_title?: string | null;
  version_label: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentListItem {
  stored_filename: string;
  metadata: Record<string, unknown>;
  checksum_sha256: string;
  tender: {
    id: string;
    reference_code: string;
    title: string;
    organization: string;
    status: string;
  } | null;
  version: DocumentVersionSummary | null;
  extracted_content: ExtractedContentSummary;
  source_trace_schema: SourceTraceSchema;
  latest_job: ProcessingJob | null;
}

export interface DocumentUploadResponse {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: PipelineStage;
  job_id: string | null;
  tender_reference: string | null;
  version_label: string | null;
  version_id: string | null;
  created_at: string;
}

export interface DocumentStatusResponse {
  document_id: string;
  status: PipelineStage;
  completed_stages: string[];
  latest_job: ProcessingJob | null;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export type DocumentVersionType =
  | "original"
  | "revision"
  | "corrigendum"
  | "addendum"
  | "clarification"
  | "annexure"
  | "other";
