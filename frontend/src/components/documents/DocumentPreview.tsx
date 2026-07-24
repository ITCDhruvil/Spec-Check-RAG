"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { SpokesLoader } from "@/components/ui/Spokes";
import { fetchDocumentFile } from "@/lib/api/documents";
import { truncateFilename } from "@/lib/truncate";
import { usePdfNavigation } from "@/lib/pdfNavigationContext";

/** pdfjs-dist requires browser APIs (DOMMatrix); never load during SSR. */
const PdfJsPreview = dynamic(
  () =>
    import("@/components/documents/PdfJsPreview").then((mod) => mod.PdfJsPreview),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center rounded-md border border-surface-border bg-surface">
        <SpokesLoader label="Loading PDF preview…" className="py-0" />
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
    collapsePreview,
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
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
        <p className="min-w-0 truncate text-xs font-medium text-ink" title={displayName}>
          {truncateFilename(displayName, 44)}
        </p>
        <div className="flex shrink-0 items-center gap-3">
          {activePage != null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent">
              Page {activePage}
            </span>
          )}
          <button
            type="button"
            onClick={() => void openInNewTab()}
            disabled={openingInTab}
            className="text-xs font-medium text-accent hover:text-accent-hover disabled:opacity-50"
          >
            {openingInTab ? "Opening…" : "Open in new tab"}
          </button>
          {collapsePreview && (
            <button
              type="button"
              onClick={collapsePreview}
              className="inline-flex items-center gap-1.5 rounded-md border border-surface-border bg-surface px-2.5 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
              aria-expanded
              aria-controls="document-preview-panel"
            >
              <svg
                className="h-3.5 w-3.5"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                aria-hidden
              >
                <path
                  d="M10 4l4 4-4 4M14 8H2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Hide
            </button>
          )}
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        {!loaded && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md border border-surface-border bg-surface">
            <SpokesLoader
              label={isDocxFile ? "Converting document for preview…" : "Loading PDF preview…"}
              className="py-0"
            />
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
