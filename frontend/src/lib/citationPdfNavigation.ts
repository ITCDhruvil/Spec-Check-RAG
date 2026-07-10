import type { PDFDocumentProxy } from "pdfjs-dist";

import {
  findHighlightRects,
  resolveHighlightPage,
  type ViewportRect,
} from "@/lib/pdfTextHighlight";

export interface ResolvedCitationLocation {
  page: number;
  rects: ViewportRect[];
}

/**
 * Locate quote in the PDF text layer. Parsed/DOCX page hints are often wrong (e.g. all p.1);
 * search hint page first, then nearby pages, then full document for smaller PDFs.
 */
export async function resolveCitationInPdf(
  doc: PDFDocumentProxy,
  pageHint: number,
  sourceText: string,
  scale: number
): Promise<ResolvedCitationLocation | null> {
  const text = sourceText.trim();
  if (!text) return null;

  const total = doc.numPages;
  const hint = Math.min(Math.max(1, pageHint), total);

  const tryPage = async (pageNum: number): Promise<ResolvedCitationLocation | null> => {
    const page = await doc.getPage(pageNum);
    const viewport = page.getViewport({ scale });
    const rects = await findHighlightRects(page, viewport, text);
    return rects.length ? { page: pageNum, rects } : null;
  };

  const onHint = await tryPage(hint);
  if (onHint) return onHint;

  const nearby = await resolveHighlightPage(doc, scale, text, hint, 15);
  if (nearby) return { page: nearby.page, rects: nearby.rects };

  // Full-doc scan — no page cap; nearby search already ran, so remaining pages
  // are checked in order. Capped by total pages only (caller decides if too large).
  for (let p = 1; p <= total; p++) {
    if (Math.abs(p - hint) <= 15) continue;
    const hit = await tryPage(p);
    if (hit) return hit;
  }

  return null;
}
