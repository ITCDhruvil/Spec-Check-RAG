import { apiClient } from "@/lib/api/client";

export type KeywordField = {
  id: string;
  label: string;
  keywords: string[];
};

export type KeywordMatch = {
  page: number;
  term: string;
  snippet: string;
  source_text: string;
};

export async function getKeywordFields(): Promise<KeywordField[]> {
  const { data } = await apiClient.get<{ fields: KeywordField[] }>(
    "/auth/keyword-fields/"
  );
  return data.fields;
}

export async function saveKeywordFields(
  fields: KeywordField[]
): Promise<KeywordField[]> {
  const { data } = await apiClient.put<{ fields: KeywordField[] }>(
    "/auth/keyword-fields/",
    { fields }
  );
  return data.fields;
}

export async function resetKeywordFields(): Promise<KeywordField[]> {
  const { data } = await apiClient.post<{ fields: KeywordField[] }>(
    "/auth/keyword-fields/reset/"
  );
  return data.fields;
}

export async function markDocumentDone(
  documentId: string,
  done: boolean
): Promise<{ marked_done: boolean; marked_done_at: string | null }> {
  const { data } = await apiClient.post(
    "/documents/" + documentId + "/mark-done/",
    { done }
  );
  return data;
}

export async function searchKeywords(
  documentId: string,
  terms: string[]
): Promise<{ matches: KeywordMatch[]; count: number }> {
  const { data } = await apiClient.get("/documents/" + documentId + "/keyword-search/", {
    params: { q: terms.join(",") },
  });
  return data;
}
