"use client";

import { useQuery } from "@tanstack/react-query";

import { getDocumentStatus } from "@/lib/api/documents";
import { TERMINAL_STAGES, type PipelineStage } from "@/lib/types/document";

export function useDocumentStatus(documentId: string, enabled = true) {
  return useQuery({
    queryKey: ["document-status", documentId],
    queryFn: () => getDocumentStatus(documentId),
    enabled: Boolean(documentId) && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status as PipelineStage | undefined;
      if (!status || TERMINAL_STAGES.includes(status)) return false;
      return 3000;
    },
  });
}
