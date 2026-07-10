/**
 * Pure geometry helpers for PDF highlight boxes.
 *
 * pdf.js reports `TextItem.width` as the *full line width* for justified text
 * and for the last run on a line, so a highlight sized from it overshoots far
 * past the actual glyphs. We can't read true glyph advances without font
 * metrics, but a run's font height is a reliable upper bound: for normal Latin
 * proportional fonts the average character advance is ~0.5em and effectively
 * never exceeds ~0.65em across a run. So `charCount * fontHeight * ratio` is a
 * safe ceiling on how wide a run of text can actually be.
 */

/** Max average character advance as a fraction of font height (em). */
export const MAX_CHAR_ADVANCE_RATIO = 0.65;

/** Absolute minimum highlight width in viewport px. */
const MIN_WIDTH = 2;

/**
 * Clamp a run's reported width to a plausible maximum for its glyph count.
 *
 * @param reportedWidth  width from pdf.js (already scaled to the viewport)
 * @param charCount      number of characters in the run (`item.str.length`)
 * @param fontHeight     run font height in viewport px (0 = unknown)
 * @returns the reported width, or the char-based ceiling when it overshoots
 */
export function clampRunWidth(
  reportedWidth: number,
  charCount: number,
  fontHeight: number
): number {
  const reported = Math.max(reportedWidth, MIN_WIDTH);

  // No font signal — cannot bound it; trust the reported width.
  if (!fontHeight || fontHeight <= 0) return reported;

  const ceiling = Math.max(
    charCount * fontHeight * MAX_CHAR_ADVANCE_RATIO,
    MIN_WIDTH
  );
  return Math.min(reported, ceiling);
}
