import { describe, expect, it } from "vitest";

import { clampRunWidth, MAX_CHAR_ADVANCE_RATIO } from "@/lib/pdfHighlightGeometry";

describe("clampRunWidth", () => {
  it("caps a justified/last-run width that spans far past the glyphs", () => {
    // "Contact:" — 8 chars, ~10px font. A sane run width is ~40px.
    // PDF reports the full justified line width (400px). Must be clamped.
    const clamped = clampRunWidth(400, 8, 10);
    const ceiling = 8 * 10 * MAX_CHAR_ADVANCE_RATIO;
    expect(clamped).toBeLessThanOrEqual(ceiling);
    expect(clamped).toBeGreaterThan(0);
  });

  it("leaves a plausible run width unchanged", () => {
    // 8 chars at 10px font → ~44px reported is realistic; keep it.
    const reported = 44;
    expect(clampRunWidth(reported, 8, 10)).toBe(reported);
  });

  it("never returns less than a 2px minimum", () => {
    expect(clampRunWidth(400, 0, 10)).toBeGreaterThanOrEqual(2);
    expect(clampRunWidth(1, 1, 10)).toBeGreaterThanOrEqual(2);
  });

  it("scales the ceiling with font size", () => {
    const small = clampRunWidth(9999, 5, 8);
    const large = clampRunWidth(9999, 5, 20);
    expect(large).toBeGreaterThan(small);
  });

  it("falls back gracefully when fontHeight is missing", () => {
    // No font signal → cannot clamp; return the reported width (still >= 2).
    expect(clampRunWidth(120, 6, 0)).toBe(120);
  });
});
