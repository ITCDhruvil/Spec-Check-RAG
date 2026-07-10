import {
  canHighlightInPdf,
  isJumpableCitation,
  normalizeCitationPage,
} from "@/lib/citationUtils";
import type { CitationHighlightTarget } from "@/lib/pdfNavigationContext";
import type { SourceCitation } from "@/lib/types/intelligence";

/** First jumpable citation with verbatim source text (for auto-highlight). */
export function getPrimaryCitationTarget(
  sources: SourceCitation[]
): CitationHighlightTarget | null {
  const prefer = [
    ...sources.filter((s) => s.highlightable !== false),
    ...sources,
  ];
  const seen = new Set<string>();
  for (const src of prefer) {
    const key = `${src.page}:${src.source_text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const page = normalizeCitationPage(src.page);
    if (!isJumpableCitation(src) || page == null) continue;
    return {
      page,
      sourceText: canHighlightInPdf(src) ? src.source_text : undefined,
    };
  }
  return null;
}

/**
 * Every jumpable, highlightable span for a field, in source order, deduped by
 * page+text. Used to highlight all spans of a multi-source field at once
 * (e.g. project_document_acquisition_note = Contact line + website URL).
 */
export function getAllCitationTargets(
  sources: SourceCitation[]
): CitationHighlightTarget[] {
  const targets: CitationHighlightTarget[] = [];
  const seen = new Set<string>();
  for (const src of sources) {
    const page = normalizeCitationPage(src.page);
    if (page == null || !isJumpableCitation(src)) continue;
    if (!canHighlightInPdf(src)) continue;
    const sourceText = src.source_text?.trim();
    if (!sourceText) continue;
    const key = `${page}:${sourceText}`;
    if (seen.has(key)) continue;
    seen.add(key);
    targets.push({ page, sourceText });
  }
  return targets;
}

/** One jump target per page (first citation on that page), sorted by page number. */
export function buildPageCitationTargets(
  sources: SourceCitation[]
): CitationHighlightTarget[] {
  const byPage = new Map<number, CitationHighlightTarget>();

  for (const src of sources) {
    const page = normalizeCitationPage(src.page);
    if (!isJumpableCitation(src) || page == null) continue;
    if (!byPage.has(page)) {
      byPage.set(page, {
        page,
        sourceText: src.source_text,
      });
    }
  }

  return Array.from(byPage.values()).sort((a, b) => a.page - b.page);
}
