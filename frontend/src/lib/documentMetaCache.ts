"use client";

import { useCallback, useEffect, useState } from "react";

const prefix = "doc-meta:";

export interface CachedDocumentMeta {
  original_filename: string;
  mime_type: string;
}

export function getCachedDocumentMeta(
  documentId: string
): CachedDocumentMeta | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(`${prefix}${documentId}`);
    if (!raw) return null;
    return JSON.parse(raw) as CachedDocumentMeta;
  } catch {
    return null;
  }
}

export function setCachedDocumentMeta(
  documentId: string,
  meta: CachedDocumentMeta
): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(`${prefix}${documentId}`, JSON.stringify(meta));
  } catch {
    // Ignore quota / private mode errors.
  }
}

/** Read sessionStorage after mount to avoid SSR/client hydration mismatches. */
export function useCachedDocumentMeta(documentId: string) {
  const [cachedMeta, setCachedMetaState] = useState<CachedDocumentMeta | null>(
    null
  );

  useEffect(() => {
    setCachedMetaState(getCachedDocumentMeta(documentId));
  }, [documentId]);

  const persistMeta = useCallback((meta: CachedDocumentMeta) => {
    setCachedDocumentMeta(documentId, meta);
    setCachedMetaState(meta);
  }, [documentId]);

  return { cachedMeta, persistMeta };
}
