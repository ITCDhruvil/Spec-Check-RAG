"use client";

import { SourceCitationList } from "@/components/summary/SourceCitationList";
import { SummaryContentBox } from "@/components/summary/SummaryContentBox";
import type { SourceCitation } from "@/lib/types/intelligence";

const NOT_FOUND = "Not found in document.";

export function SummaryTextBlock({
  text,
  sources,
}: {
  text?: string;
  sources?: SourceCitation[];
}) {
  const content = text?.trim();

  if (!content) {
    return <p className="text-sm italic text-ink-muted">{NOT_FOUND}</p>;
  }

  return (
    <SummaryContentBox>
      <SourceCitationList signal={content} sources={sources} />
    </SummaryContentBox>
  );
}
