export interface ChatCitation {
  chunk_id: string;
  page: number | null;
  section: string;
  source_text: string;
  relevance: number;
  highlightable?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: ChatCitation[];
  retrieval_chunks: Array<{
    chunk_id: string;
    page_start: number;
    page_end: number;
    section_title: string;
    score: number;
  }>;
  token_usage: Record<string, number>;
  model_metadata: Record<string, unknown>;
  created_at: string;
}

export interface ChatSession {
  id: string;
  document_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface ChatIndexStatus {
  document_id: string;
  indexed: boolean;
  chunk_count?: number;
  embedding_model?: string;
  indexed_at?: string;
}

export interface SendMessageResponse {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  follow_up_questions?: string[];
}
