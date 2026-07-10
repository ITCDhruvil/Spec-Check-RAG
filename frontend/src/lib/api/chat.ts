import { apiClient } from "@/lib/api/client";
import type {
  ChatIndexStatus,
  ChatSession,
  ChatSessionDetail,
  SendMessageResponse,
} from "@/lib/types/chat";

export async function getChatIndexStatus(
  documentId: string
): Promise<ChatIndexStatus> {
  const { data } = await apiClient.get<ChatIndexStatus>(
    `/documents/${documentId}/chat/index/`
  );
  return data;
}

export async function indexDocumentForChat(
  documentId: string
): Promise<ChatIndexStatus & { message: string }> {
  const { data } = await apiClient.post(
    `/documents/${documentId}/chat/index/`
  );
  return data;
}

export async function listChatSessions(
  documentId: string
): Promise<ChatSession[]> {
  const { data } = await apiClient.get<ChatSession[]>(
    `/documents/${documentId}/chat/sessions/`
  );
  return data;
}

export async function createChatSession(
  documentId: string,
  title = ""
): Promise<ChatSession> {
  const { data } = await apiClient.post<ChatSession>(
    `/documents/${documentId}/chat/sessions/`,
    { title }
  );
  return data;
}

export async function getChatSession(
  documentId: string,
  sessionId: string
): Promise<ChatSessionDetail> {
  const { data } = await apiClient.get<ChatSessionDetail>(
    `/documents/${documentId}/chat/sessions/${sessionId}/`
  );
  return data;
}

export async function sendChatMessage(
  documentId: string,
  sessionId: string,
  message: string
): Promise<SendMessageResponse> {
  const { data } = await apiClient.post<SendMessageResponse>(
    `/documents/${documentId}/chat/sessions/${sessionId}/messages/`,
    { message }
  );
  return data;
}
