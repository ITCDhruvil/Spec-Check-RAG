import type { CitationHighlightTarget } from "@/lib/pdfNavigationContext";
import type { SourceCitation } from "@/lib/types/intelligence";

/** Coerce API/LLM page values (number or string) to a 1-based page index. */
export function normalizeCitationPage(page: unknown): number | undefined {
  if (page == null || page === "") return undefined;
  const n = typeof page === "number" ? page : parseInt(String(page), 10);
  return Number.isFinite(n) && n >= 1 ? n : undefined;
}

export function normalizeHighlightTarget(
  target: CitationHighlightTarget
): CitationHighlightTarget | null {
  const page = normalizeCitationPage(target.page);
  if (!page) return null;
  const sourceText = target.sourceText?.trim();
  return { page, sourceText: sourceText || undefined };
}

/** Citation can jump/highlight in PDF preview only when quote is grounded in the document. */
export function isJumpableCitation(src: SourceCitation): boolean {
  return (
    Boolean(src.source_text?.trim()) &&
    src.citation_verified !== false &&
    normalizeCitationPage(src.page) != null
  );
}

/** PDF.js can draw highlight boxes for this quote (snapped to page text layer). */
export function canHighlightInPdf(src: SourceCitation): boolean {
  return isJumpableCitation(src) && src.highlightable !== false;
}