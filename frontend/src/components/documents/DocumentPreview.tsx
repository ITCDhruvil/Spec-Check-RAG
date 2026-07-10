"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDocumentFile } from "@/lib/api/documents";
import { usePdfNavigation } from "@/lib/pdfNavigationContext";

/** pdfjs-dist requires browser APIs (DOMMatrix); never load during SSR. */
const PdfJsPreview = dynamic(
  () =>
    import("@/components/documents/PdfJsPreview").then((mod) => mod.PdfJsPreview),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center rounded-md border border-surface-border bg-surface">
        <p className="text-sm text-ink-muted">Loading PDF preview…</p>
      </div>
    ),
  }
);

const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const DOCX_PREVIEW_UNAVAILABLE =
  "Word preview is not ready. Install LibreOffice (set LIBREOFFICE_PATH in backend .env) or Microsoft Word on Windows (DOCX_PREVIEW_USE_WORD=True), restart the server, then refresh this page.";

interface DocumentPreviewProps {
  documentId: string;
  filename?: string;
  mimeType?: string;
}

function isDocx(filename?: string, mimeType?: string): boolean {
  return (
    mimeType === DOCX_MIME || Boolean(filename?.toLowerCase().endsWith(".docx"))
  );
}

export function DocumentPreview({
  documentId,
  filename,
  mimeType,
}: DocumentPreviewProps) {
  const isDocxFile = isDocx(filename, mimeType);
  const previewVariant = isDocxFile ? "preview-pdf" : "file";
  const [loaded, setLoaded] = useState(false);
  const [openingInTab, setOpeningInTab] = useState(false);
  const {
    previewContainerRef,
    activePage,
    activeHighlight,
    activeHighlights,
    flashKey,
    registerScrollToCitation,
    unregisterScrollToCitation,
  } = usePdfNavigation();
  const previewWrapperRef = useRef<HTMLDivElement | null>(null);
  const flashTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLoaded(false);
  }, [documentId, previewVariant]);

  useEffect(() => {
    if (flashKey === 0) return;
    const el = previewWrapperRef.current;
    if (!el) return;

    el.classList.remove("animate-preview-flash");
    void el.offsetWidth;
    el.classList.add("animate-preview-flash");

    if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
    flashTimeoutRef.current = setTimeout(() => {
      el.classList.remove("animate-preview-flash");
    }, 1300);

    return () => {
      if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
    };
  }, [flashKey]);

  const dismissLoadingOverlay = useCallback(() => setLoaded(true), []);

  const openInNewTab = useCallback(async () => {
    if (openingInTab) return;
    setOpeningInTab(true);
    try {
      const data = await fetchDocumentFile(documentId, previewVariant);
      const blob = new Blob([data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      // PdfJsPreview already surfaces load errors; keep button silent on failure.
    } finally {
      setOpeningInTab(false);
    }
  }, [documentId, openingInTab, previewVariant]);

  const displayName = filename ?? "Loading…";

  return (
    <div ref={previewContainerRef} className="flex h-full min-h-[320px] flex-col">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Document preview</h3>
          <p className="mt-0.5 truncate text-xs text-ink-muted">{displayName}</p>
        </div>
        <div className="flex items-center gap-3">
          {activePage != null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent">
              Page {activePage}
            </span>
          )}
          <button
            type="button"
            onClick={() => void openInNewTab()}
            disabled={openingInTab}
            className="shrink-0 text-xs font-medium text-accent hover:text-accent-hover disabled:opacity-50"
          >
            {openingInTab ? "Opening…" : "Open in new tab"}
          </button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        {!loaded && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md border border-surface-border bg-surface">
            <p className="text-sm text-ink-muted">
              {isDocxFile ? "Converting document for preview…" : "Loading PDF preview…"}
            </p>
          </div>
        )}
        <PdfJsPreview
          documentId={documentId}
          previewVariant={previewVariant}
          activeHighlight={activeHighlight}
          activeHighlights={activeHighlights}
          flashKey={flashKey}
          onReady={dismissLoadingOverlay}
          onLoadFailed={dismissLoadingOverlay}
          onRegisterNavigator={registerScrollToCitation}
          onUnregisterNavigator={unregisterScrollToCitation}
          wrapperRef={previewWrapperRef}
          unavailableMessage={isDocxFile ? DOCX_PREVIEW_UNAVAILABLE : undefined}
        />
      </div>
    </div>
  );
}
