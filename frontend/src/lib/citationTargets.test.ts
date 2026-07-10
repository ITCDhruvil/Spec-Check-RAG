import { describe, expect, it } from "vitest";

import {
  getAllCitationTargets,
  getPrimaryCitationTarget,
} from "@/lib/citationTargets";
import type { SourceCitation } from "@/lib/types/intelligence";

// Reproduces the project_document_acquisition_note bug: one field, several
// verbatim source spans (Contact line + website URL + a third source), all on
// the same page. Only the first span was ever highlighted; the rest were shown
// as "(+2 more)" in the panel but never jumped-to or highlighted.
const MULTI_SOURCE: SourceCitation[] = [
  {
    page: 1,
    section: "Cover / Front Matter",
    source_text: "Contact: Bernardo Iniguez, Director of Public Works/Facilities",
    citation_verified: true,
    highlightable: true,
  },
  {
    page: 1,
    section: "Cover / Front Matter",
    source_text:
      "Copies of the Plans, Specifications, and contract documents are available on the City's website at https://www.bellgardens.org/i-want-to/view-bids-rfps/rfps-and-bids",
    citation_verified: true,
    highlightable: true,
  },
  {
    page: 2,
    section: "Instructions to Bidders",
    source_text: "Documents may be obtained from the City Clerk's office.",
    citation_verified: true,
    highlightable: true,
  },
];

describe("getAllCitationTargets", () => {
  it("returns every jumpable, highlightable span for a multi-source field", () => {
    const targets = getAllCitationTargets(MULTI_SOURCE);
    expect(targets).toHaveLength(3);
    expect(targets.map((t) => t.sourceText)).toEqual([
      MULTI_SOURCE[0].source_text,
      MULTI_SOURCE[1].source_text,
      MULTI_SOURCE[2].source_text,
    ]);
    expect(targets.map((t) => t.page)).toEqual([1, 1, 2]);
  });

  it("skips unverified / non-highlightable / pageless sources", () => {
    const sources: SourceCitation[] = [
      { page: 1, source_text: "verified verbatim quote here", citation_verified: true },
      { page: 1, source_text: "phantom text", citation_verified: false },
      { page: undefined, source_text: "no page", citation_verified: true },
      { page: 3, source_text: "", citation_verified: true },
    ];
    const targets = getAllCitationTargets(sources);
    expect(targets).toHaveLength(1);
    expect(targets[0].sourceText).toBe("verified verbatim quote here");
  });

  it("dedupes identical page+text spans", () => {
    const dup: SourceCitation[] = [
      { page: 1, source_text: "same quote", citation_verified: true },
      { page: 1, source_text: "same quote", citation_verified: true },
    ];
    expect(getAllCitationTargets(dup)).toHaveLength(1);
  });

  it("still exposes the first span as the primary (scroll anchor)", () => {
    const primary = getPrimaryCitationTarget(MULTI_SOURCE);
    expect(primary?.sourceText).toBe(MULTI_SOURCE[0].source_text);
    expect(primary?.page).toBe(1);
  });
});
