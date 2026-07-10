"use client";

import { useState } from "react";

import { deadlineDisplayLabel, resolveDeadlineDisplay } from "@/lib/deadlineDisplay";
import type { ExtractedInsightItem, SourceCitation, SummarySectionBlock } from "@/lib/types/intelligence";

import { CitationPanel, CitationToggle } from "./SourceCitationList";

type DeadlineInput = SummarySectionBlock | ExtractedInsightItem;

function toDisplayInput(item: DeadlineInput, sources?: SourceCitation[]) {
  if ("requirement" in item && item.requirement) {
    return {
      requirement: item.requirement,
      date_time: item.date_time,
      value: item.value,
      sourceText: item.source_text,
      sources,
    };
  }
  const block = item as SummarySectionBlock;
  return {
    text: block.text,
    item: block.item,
    date: block.date,
    sources: block.sources ?? sources,
  };
}

export function DeadlineItemRow({
  item,
  index,
  sources,
  showSources = false,
  confidenceBadge,
}: {
  item: DeadlineInput;
  index: number;
  sources?: SourceCitation[];
  showSources?: boolean;
  confidenceBadge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const citSources =
    sources ??
    ("sources" in item ? item.sources : undefined) ??
    (item.source_text
      ? [
          {
            page: "page" in item ? item.page : undefined,
            section: "section" in item ? item.section : undefined,
            section_path: "section_path" in item ? item.section_path : undefined,
            source_text: item.source_text,
          },
        ]
      : undefined);

  const { label, value } = resolveDeadlineDisplay(toDisplayInput(item, citSources));
  const displayLabel = deadlineDisplayLabel(label);
  const hasCitations = Boolean(citSources?.length);

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-2.5">
        <span
          className="w-5 shrink-0 pt-0.5 text-right text-xs font-medium tabular-nums text-ink-muted"
          aria-hidden
        >
          {index + 1}.
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-relaxed text-ink">
                <span className="font-semibold">{displayLabel}:</span>
                {value ? (
                  <span className="mt-1 block font-normal text-ink-muted">
                    {value}
                  </span>
                ) : (
                  <span className="mt-1 block text-xs italic text-ink-muted">
                    See citation for details
                  </span>
                )}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {hasCitations && (
                <CitationToggle
                  open={open}
                  count={citSources!.length}
                  onToggle={() => setOpen((v) => !v)}
                />
              )}
              {confidenceBadge}
            </div>
          </div>
          {open && hasCitations && (
            <CitationPanel sources={citSources!} />
          )}
        </div>
      </div>
    </li>
  );
}
