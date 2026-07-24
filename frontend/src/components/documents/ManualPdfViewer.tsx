"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import * as pdfjs from "pdfjs-dist";
// pdf.js web-viewer styles (text layer, find highlights). Side-effect import.
import "pdfjs-dist/web/pdf_viewer.css";

import { fetchDocumentFile } from "@/lib/api/documents";
import { SpokesLoader } from "@/components/ui/Spokes";

if (typeof window !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

export type ManualSearchState = {
  current: number; // 1-based; 0 when none
  total: number;
};

export type ManualPdfHandle = {
  /** Highlight all matches for the query; jump to the first. */
  search: (query: string) => void;
  /** Step to next/prev match. */
  next: () => void;
  prev: () => void;
  /** Clear highlights. */
  clear: () => void;
};

type ViewerBundle = {
  eventBus: import("pdfjs-dist/web/pdf_viewer.mjs").EventBus;
  findController: import("pdfjs-dist/web/pdf_viewer.mjs").PDFFindController;
  viewer: import("pdfjs-dist/web/pdf_viewer.mjs").PDFViewer;
};

export const ManualPdfViewer = forwardRef<
  ManualPdfHandle,
  {
    documentId: string;
    onSearchState?: (s: ManualSearchState) => void;
  }
>(function ManualPdfViewer({ documentId, onSearchState }, ref) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bundleRef = useRef<ViewerBundle | null>(null);
  const queryRef = useRef<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let pdfDoc: import("pdfjs-dist").PDFDocumentProxy | null = null;

    async function boot() {
      setLoading(true);
      setError(null);
      try {
        // The web viewer scaffold — loaded dynamically (browser-only).
        const viewerMod = await import("pdfjs-dist/web/pdf_viewer.mjs");

        const container = containerRef.current;
        if (!container || cancelled) return;

        const eventBus = new viewerMod.EventBus();
        const linkService = new viewerMod.PDFLinkService({ eventBus });
        const findController = new viewerMod.PDFFindController({
          eventBus,
          linkService,
        });
        const viewer = new viewerMod.PDFViewer({
          container,
          eventBus,
          linkService,
          findController,
          textLayerMode: 2, // enable text layer (required for search)
        });
        linkService.setViewer(viewer);

        // Surface match counts to the caller.
        eventBus.on(
          "updatefindmatchescount",
          (evt: { matchesCount: { current: number; total: number } }) => {
            onSearchState?.({
              current: evt.matchesCount.current,
              total: evt.matchesCount.total,
            });
          }
        );
        eventBus.on(
          "updatefindcontrolstate",
          (evt: { matchesCount: { current: number; total: number } }) => {
            onSearchState?.({
              current: evt.matchesCount.current,
              total: evt.matchesCount.total,
            });
          }
        );

        const data = await fetchDocumentFile(documentId, "file");
        if (cancelled) return;
        pdfDoc = await pdfjs.getDocument({ data }).promise;
        if (cancelled) {
          void pdfDoc.destroy();
          return;
        }
        viewer.setDocument(pdfDoc);
        linkService.setDocument(pdfDoc, null);

        bundleRef.current = { eventBus, findController, viewer };
        setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load the PDF.");
          setLoading(false);
        }
      }
    }

    void boot();
    return () => {
      cancelled = true;
      if (pdfDoc) void pdfDoc.destroy();
      bundleRef.current = null;
    };
  }, [documentId, onSearchState]);

  useImperativeHandle(
    ref,
    () => ({
      search(query: string) {
        queryRef.current = query;
        bundleRef.current?.eventBus.dispatch("find", {
          source: null,
          type: "",
          query,
          caseSensitive: false,
          entireWord: false,
          highlightAll: true,
          findPrevious: false,
          matchDiacritics: false,
        });
      },
      next() {
        bundleRef.current?.eventBus.dispatch("find", {
          source: null,
          type: "again",
          query: queryRef.current,
          caseSensitive: false,
          entireWord: false,
          highlightAll: true,
          findPrevious: false,
          matchDiacritics: false,
        });
      },
      prev() {
        bundleRef.current?.eventBus.dispatch("find", {
          source: null,
          type: "again",
          query: queryRef.current,
          caseSensitive: false,
          entireWord: false,
          highlightAll: true,
          findPrevious: true,
          matchDiacritics: false,
        });
      },
      clear() {
        queryRef.current = "";
        bundleRef.current?.eventBus.dispatch("find", {
          source: null,
          type: "",
          query: "",
          highlightAll: false,
        });
      },
    }),
    []
  );

  return (
    <div className="relative h-full min-h-0 overflow-hidden rounded-md border border-surface-border bg-surface-muted/40">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface">
          <SpokesLoader label="Loading PDF…" className="py-0" />
        </div>
      )}
      {error && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface p-6 text-center text-sm text-red-600 dark:text-red-300">
          {error}
        </div>
      )}
      {/* pdf.js viewer requires an absolutely-positioned container. */}
      <div ref={containerRef} className="pdfViewerContainer absolute inset-0 overflow-auto">
        <div className="pdfViewer" />
      </div>
    </div>
  );
});
