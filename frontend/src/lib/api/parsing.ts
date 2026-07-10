import { apiClient } from "@/lib/api/client";
import type {
  DocumentPageItem,
  DocumentSectionItem,
  ParsedDocumentDetail,
  ParsingStatusResponse,
} from "@/lib/types/parsing";

export async function getParsedDocument(
  documentId: string
): Promise<ParsedDocumentDetail> {
  const { data } = await apiClient.get<ParsedDocumentDetail>(
    `/documents/${documentId}/parsed/`
  );
  return data;
}

export async function getParsingStatus(
  documentId: string
): Promise<ParsingStatusResponse> {
  const { data } = await apiClient.get<ParsingStatusResponse>(
    `/documents/${documentId}/parsed/status/`
  );
  return data;
}

export async function listParsedPages(
  documentId: string
): Promise<DocumentPageItem[]> {
  const { data } = await apiClient.get<DocumentPageItem[]>(
    `/documents/${documentId}/parsed/pages/`
  );
  return data;
}

export async function getParsedPage(
  documentId: string,
  pageNumber: number
): Promise<DocumentPageItem> {
  const { data } = await apiClient.get<DocumentPageItem>(
    `/documents/${documentId}/parsed/pages/${pageNumber}/`
  );
  return data;
}

export async function listParsedSections(
  documentId: string
): Promise<DocumentSectionItem[]> {
  const { data } = await apiClient.get<DocumentSectionItem[]>(
    `/documents/${documentId}/parsed/sections/`
  );
  return data;
}
