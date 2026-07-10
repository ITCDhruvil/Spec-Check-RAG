import * as pdfjs from "pdfjs-dist";
import type { PDFPageProxy } from "pdfjs-dist";
import type { PageViewport } from "pdfjs-dist/types/src/display/display_utils";
import type { TextItem } from "pdfjs-dist/types/src/display/api";

import { clampRunWidth } from "@/lib/pdfHighlightGeometry";

export interface ViewportRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface TextSpan {
  start: number;
  end: number;
  item: TextItem;
  itemIndex: number;
}

interface ViewportMetrics {
  x: number;
  y: number;
  fontHeight: number;
  scaleX: number;
}

const LINE_Y_THRESHOLD = 3;
const ADJACENT_X_GAP = 2;

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .replace(/\u00ad/g, "")
    .replace(/-\s*\n\s*/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .replace(/[""„"]/g, '"')
    .replace(/[''‚']/g, "'")
    .replace(/\uFFFD/g, "")
    .replace(/[^\w\s"'.,;:$%()/\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getViewportMetrics(
  item: TextItem,
  viewport: PageViewport
): ViewportMetrics {
  const transform = pdfjs.Util.transform(viewport.transform, item.transform);
  const scaleX = Math.abs(transform[0]) || 1;
  const fontHeight =
    Math.hypot(transform[2], transform[3]) ||
    Math.hypot(transform[0], transform[1]) ||
    12;

  return {
    x: transform[4],
    y: transform[5],
    fontHeight,
    scaleX,
  };
}

/**
 * PDF item.width is often the full line width (justified text). Use the distance
 * to the next glyph run on the same line when it yields a tighter bound.
 */
function computeEffectiveWidths(
  items: TextItem[],
  viewport: PageViewport
): number[] {
  const metrics = items.map((item) => getViewportMetrics(item, viewport));
  const widths: number[] = [];

  for (let i = 0; i < items.length; i++) {
    const m = metrics[i];
    // Hard ceiling from glyph count × font height — bounds justified/last-run
    // widths that pdf.js reports as the full line width (fixes over-wide boxes).
    const reported = clampRunWidth(
      Math.max(items[i].width * m.scaleX, 2),
      items[i].str.length,
      m.fontHeight
    );
    let effective = reported;

    for (let j = i + 1; j < items.length; j++) {
      const nj = metrics[j];
      if (Math.abs(nj.y - m.y) > LINE_Y_THRESHOLD) break;
      if (nj.x <= m.x + ADJACENT_X_GAP) continue;

      const gap = nj.x - m.x;
      if (gap > 0) {
        effective = Math.min(effective, gap - 1);
      }
      break;
    }

    widths[i] = Math.max(effective, 2);
  }

  const charWidths: number[] = [];
  for (let i = 0; i < items.length; i++) {
    const len = items[i].str.trim().length;
    if (len < 2) continue;
    charWidths.push(widths[i] / items[i].str.length);
  }
  charWidths.sort((a, b) => a - b);
  const medianChar =
    charWidths[Math.floor(charWidths.length / 2)] ?? null;

  if (medianChar != null) {
    for (let i = 0; i < items.length; i++) {
      const len = items[i].str.length;
      if (len < 1) continue;
      const perChar = widths[i] / len;
      if (perChar > medianChar * 2.2) {
        widths[i] = Math.min(widths[i], Math.ceil(len * medianChar * 1.08));
      }
    }
  }

  return widths;
}

/** Highlight only [charStart, charEnd) using measured run width, not full line width. */
function itemSubstringRect(
  item: TextItem,
  viewport: PageViewport,
  charStart: number,
  charEnd: number,
  effectiveWidth: number
): ViewportRect {
  const m = getViewportMetrics(item, viewport);
  const len = item.str.length;
  const top = m.y - m.fontHeight;
  const height = m.fontHeight * 1.12;

  if (len <= 0) {
    return { left: m.x, top, width: effectiveWidth, height };
  }

  const start = Math.max(0, Math.min(charStart, len));
  const end = Math.max(start, Math.min(charEnd, len));
  const startFrac = start / len;
  const endFrac = end / len;

  const width = Math.max(effectiveWidth * (endFrac - startFrac), 2);
  const left = m.x + effectiveWidth * startFrac;

  const maxRight = viewport.width - 2;
  const clampedWidth = Math.min(width, Math.max(maxRight - left, 2));

  return {
    left: Math.round(left * 10) / 10,
    top: Math.round(top * 10) / 10,
    width: Math.round(clampedWidth * 10) / 10,
    height: Math.round(height * 10) / 10,
  };
}

function findMatchRange(
  haystack: string,
  needle: string
): { start: number; end: number } | null {
  const h = normalizeText(haystack);
  const n = normalizeText(needle);
  if (!n || !h) return null;

  let idx = h.indexOf(n);
  if (idx >= 0) return { start: idx, end: idx + n.length };

  const words = n.split(" ").filter(Boolean);
  const minWords = Math.min(6, Math.max(3, Math.ceil(words.length * 0.4)));

  for (let w = words.length; w >= minWords; w--) {
    const prefix = words.slice(0, w).join(" ");
    idx = h.indexOf(prefix);
    if (idx >= 0) return { start: idx, end: idx + prefix.length };
  }

  for (let w = words.length; w >= minWords; w--) {
    const suffix = words.slice(-w).join(" ");
    idx = h.indexOf(suffix);
    if (idx >= 0) return { start: idx, end: idx + suffix.length };
  }

  if (n.length >= 20) {
    for (const len of [48, 32, 24, 20]) {
      if (n.length < len) continue;
      const slice = n.slice(0, len);
      idx = h.indexOf(slice);
      if (idx >= 0) return { start: idx, end: idx + slice.length };
    }
  }

  if (words.length >= 3) {
    const anchor = words.slice(0, 3).join(" ");
    if (anchor.length >= 12) {
      idx = h.indexOf(anchor);
      if (idx >= 0) {
        return { start: idx, end: idx + Math.min(n.length, anchor.length + 40) };
      }
    }
  }

  return null;
}

function buildPageTextMap(
  items: TextItem[]
): { fullText: string; spans: TextSpan[] } {
  let fullText = "";
  const spans: TextSpan[] = [];

  items.forEach((item, itemIndex) => {
    const start = fullText.length;
    fullText += item.str;
    spans.push({ start, end: fullText.length, item, itemIndex });
    fullText += " ";
  });

  return { fullText, spans };
}

/** Search nearby pages when the chunk page hint does not match the PDF text layer. */
export async function resolveHighlightPage(
  doc: import("pdfjs-dist").PDFDocumentProxy,
  scale: number,
  searchText: string,
  pageHint: number,
  radius = 3
): Promise<{ page: number; rects: ViewportRect[] } | null> {
  const order: number[] = [];
  for (let d = 0; d <= radius; d++) {
    if (d === 0) order.push(0);
    else {
      order.push(d, -d);
    }
  }

  for (const delta of order) {
    const pageNum = pageHint + delta;
    if (pageNum < 1 || pageNum > doc.numPages) continue;
    const page = await doc.getPage(pageNum);
    const viewport = page.getViewport({ scale });
    const rects = await findHighlightRects(page, viewport, searchText);
    if (rects.length) {
      return { page: pageNum, rects };
    }
  }
  return null;
}

export async function findHighlightRects(
  page: PDFPageProxy,
  viewport: PageViewport,
  searchText: string
): Promise<ViewportRect[]> {
  if (!searchText.trim()) return [];

  const textContent = await page.getTextContent();
  const items = textContent.items.filter(
    (item): item is TextItem => "str" in item && Boolean(item.str?.trim())
  );

  if (!items.length) return [];

  const effectiveWidths = computeEffectiveWidths(items, viewport);
  const { fullText, spans } = buildPageTextMap(items);
  const match = findMatchRange(fullText, searchText);
  if (!match) return [];

  const rects: ViewportRect[] = [];

  for (const span of spans) {
    if (span.end <= match.start || span.start >= match.end) continue;

    const charStart = Math.max(0, match.start - span.start);
    const charEnd = Math.min(span.item.str.length, match.end - span.start);
    if (charEnd <= charStart) continue;

    rects.push(
      itemSubstringRect(
        span.item,
        viewport,
        charStart,
        charEnd,
        effectiveWidths[span.itemIndex]
      )
    );
  }

  // Keep separate boxes per text run — do not merge into full-line strips.
  return rects;
}
