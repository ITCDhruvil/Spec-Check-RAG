"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { DocumentPreview } from "@/components/documents/DocumentPreview";
import { SplitPanelLayout } from "@/components/layout/SplitPanelLayout";
import { getDocument } from "@/lib/api/documents";
import { useCachedDocumentMeta } from "@/lib/documentMetaCache";
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

  const pageHeader = (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <Link
          href={`/documents/${documentId}/summary`}
          className="text-xs text-ink-muted hover:text-ink"
        >
          ← Specification briefing
        </Link>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          Ask about this tender
        </h2>
        <p className="mt-1 text-sm text-ink-muted">{resolvedFilename}</p>
      </div>
      <Link
        href={`/documents/${documentId}/summary`}
        className="rounded-md border border-surface-border bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
      >
        View briefing
      </Link>
    </div>
  );

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
      <SplitPanelLayout
        header={pageHeader}
        left={chatPanel}
        right={previewPanel}
      />
    </PdfNavigationProvider>
  );
}
