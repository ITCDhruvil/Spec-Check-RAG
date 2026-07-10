"use client";

import { DeadlineItemRow } from "@/components/summary/DeadlineItemRow";
import { SourceCitationList } from "@/components/summary/SourceCitationList";
import { SummaryContentBox } from "@/components/summary/SummaryContentBox";
import type { SummarySectionBlock } from "@/lib/types/intelligence";

export function SummaryItemsList({
  items,
  variant = "default",
  showSources = true,
}: {
  items: SummarySectionBlock[];
  variant?: "default" | "deadline";
  showSources?: boolean;
}) {
  if (!items.length) return null;

  return (
    <SummaryContentBox>
      <ul className="divide-y divide-surface-border/80">
        {items.map((item, i) => {
          if (!item.text && !item.item && !item.sources?.length) return null;

          if (variant === "deadline") {
            return (
              <DeadlineItemRow
                key={i}
                item={item}
                index={i}
                showSources={showSources}
              />
            );
          }

          const text = item.text || item.item;
          const subtext = item.date ? `Date: ${item.date}` : undefined;

          return (
            <li key={i} className="py-3 first:pt-0 last:pb-0">
              <SourceCitationList
                signal={text ?? "—"}
                subtext={subtext}
                sources={item.sources}
              />
            </li>
          );
        })}
      </ul>
    </SummaryContentBox>
  );
}
