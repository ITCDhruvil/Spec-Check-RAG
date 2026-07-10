export type SummaryStatus = "pending" | "processing" | "completed" | "failed";

export interface SourceCitation {
  page?: number;
  section?: string;
  section_path?: string;
  source_text?: string;
  /** True when source_text was found verbatim in parsed document pages. */
  citation_verified?: boolean;
  /** True when source_text can be located in the PDF text layer for highlight. */
  highlightable?: boolean;
}

export interface SummarySectionBlock {
  text?: string;
  item?: string;
  date?: string | null;
  /** Stable field identifier for spec-check rows (Phase 5). */
  field_key?: string;
  /** Per-field confidence 0–100 from extraction grounding (Phase 5). */
  confidence?: number;
  /** critical | medium | low — penalties/risks financial-impact tier */
  severity?: string | null;
  /** Submission checklist grouping (see submissionChecklist.ts). */
  category?: string;
  sources?: SourceCitation[];
  /** Raw source text from extraction grounding (may be present on older rows without sources array). */
  source_text?: string;
  /** True when the date was calculated by the post-processor, not read from the document. */
  _calculated?: boolean;
  /** Calendar-day offset used for the calculation (30 or 60). */
  _days_offset?: number;
  /** True when project value was absent — UI should show the value input box. */
  _awaiting_project_value?: boolean;
  /** Source field_key when this row is a product alias (e.g. award_date). */
  _alias_of?: string;
  /** absolute | duration | estimated — set by Phase 6 post-rules. */
  _date_kind?: string;
  /** Number of document chunks merged into this project_description value. */
  _scope_chunk_count?: number;
  /** True when project_description was clipped at the max-length cap. */
  _scope_truncated?: boolean;
}

export interface SpecCheckFields {
  project_metadata_items?: SummarySectionBlock[];
  project_people_items?: SummarySectionBlock[];
  project_size_location_items?: SummarySectionBlock[];
  project_dates?: SummarySectionBlock[];
  bond_items?: SummarySectionBlock[];
  set_aside_items?: SummarySectionBlock[];
}

export interface GeneratedSummaryData {
  spec_check_fields?: SpecCheckFields;
  _meta?: Record<string, unknown>;
}

export interface GeneratedSummary {
  id: string;
  document_id: string;
  status: SummaryStatus;
  version: number;
  is_current: boolean;
  summary_json: GeneratedSummaryData;
  model_metadata: Record<string, unknown>;
  total_tokens: number;
  error_message: string;
  last_error: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExtractedInsightItem {
  requirement: string;
  page: number;
  section: string;
  section_path?: string;
  source_text: string;
  confidence: number;
  citation_verified?: boolean;
  /** Submission deadlines: calendar date/time or portal URL from the document. */
  date_time?: string | null;
  value?: string | null;
  label?: string | null;
  /** Penalties & risks: critical (financial) | medium | low */
  severity?: string | null;
}

export interface ExtractedInsight {
  id: string;
  extraction_type: string;
  payload: { items: ExtractedInsightItem[] };
  confidence_score: number;
  model_name: string;
  prompt_version: string;
  token_usage: Record<string, number>;
  item_count: number;
  created_at: string;
}

export interface SummaryStatusResponse {
  document_id: string;
  document_status: string;
  summary_status: SummaryStatus | null;
  summary_id: string | null;
  version: number | null;
  progress_stage: string | null;
  total_tokens: number | null;
  error_message?: string | null;
}

export interface GenerateSummaryResponse {
  message: string;
  document_id: string;
  celery_task_id?: string;
  summary_id?: string;
  regenerate?: boolean;
  sync?: boolean;
  status?: string;
}
