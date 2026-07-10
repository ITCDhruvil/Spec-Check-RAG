export type ParsingStatus = "pending" | "processing" | "completed" | "failed";

export interface ParsedDocumentSummary {
  id: string;
  document_id: string;
  parsing_status: ParsingStatus;
  total_pages: number;
  parsing_quality_score: number;
  ocr_pages: number;
  tables_count: number;
  parsing_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ParsedDocumentDetail extends ParsedDocumentSummary {
  raw_text_preview: string;
  structured_text_preview: string;
}

export interface DocumentPageItem {
  id: string;
  page_number: number;
  extracted_text: string;
  extraction_method: string;
  ocr_used: boolean;
  quality_score: number;
  created_at: string;
}

export interface DocumentSectionItem {
  id: string;
  title: string;
  content: string;
  page_start: number;
  page_end: number;
  section_order: number;
  created_at: string;
}

export interface ParsingStatusResponse {
  document_id: string;
  document_status: string;
  parsing_status: ParsingStatus | null;
  parsing_quality_score: number | null;
  total_pages: number | null;
  ocr_pages: number;
  latest_job: Record<string, unknown> | null;
}
