"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { DocumentPreview } from "@/components/documents/DocumentPreview";
import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";
import { getDocument } from "@/lib/api/documents";
import { useCachedDocumentMeta } from "@/lib/documentMetaCache";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { PdfNavigationProvider } from "@/lib/pdfNavigationContext";

export default function DocumentChatPage() {
  const params = useParams();
  const documentId = String(params.id);
  const { cachedMeta, persistMeta } = useCachedDocumentMeta(documentId);

  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
  });

  useEffect(() => {
    const doc = documentQuery.data;
    if (!doc?.original_filename || !doc.mime_type) return;
    persistMeta({
      original_filename: doc.original_filename,
      mime_type: doc.mime_type,
    });
  }, [documentId, documentQuery.data, persistMeta]);

  const resolvedFilename =
    documentQuery.data?.original_filename ??
    cachedMeta?.original_filename ??
    "Your document";
  const resolvedMimeType =
    documentQuery.data?.mime_type ?? cachedMeta?.mime_type;

  // Page header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: `/documents/${documentId}/summary`,
    backLabel: "Specification briefing",
    title: "Ask about this tender",
    subtitle: resolvedFilename,
  });

  const chatPanel = (
    <div className="flex h-full min-h-[420px] flex-col">
      {documentQuery.isError && (
        <p className="mb-4 text-sm text-red-600">
          {(documentQuery.error as Error).message}
        </p>
      )}
      <ChatPanel documentId={documentId} />
    </div>
  );

  const previewPanel = (
    <div className="h-full min-h-0">
      <DocumentPreview
        documentId={documentId}
        filename={resolvedFilename !== "Your document" ? resolvedFilename : undefined}
        mimeType={resolvedMimeType}
      />
    </div>
  );

  return (
    <PdfNavigationProvider>
      <SplitPanelLayout left={chatPanel} right={previewPanel} />
    </PdfNavigationProvider>
  );
}
