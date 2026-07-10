"use client";

import { useState, useCallback, useMemo } from "react";

import { SummaryContentBox } from "@/components/summary/SummaryContentBox";
import { DeadlineItemRow } from "@/components/summary/DeadlineItemRow";
import { SpecFieldRow } from "@/components/summary/SpecFieldRow";
import type { GeneratedSummaryData, SummarySectionBlock } from "@/lib/types/intelligence";
import { confidenceTone } from "@/lib/insightCategories";
import { sortMetadataItems } from "@/lib/specFieldLabels";

const NOT_FOUND = "Not found in document.";

function parseDollarAmount(text: string): number | null {
  const pattern = /\$([\d,]+(?:\.\d+)?)\s*(million|M|billion|B|thousand|K)?/gi;
  const amounts: number[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    let val = parseFloat(match[1].replace(/,/g, ""));
    const suffix = (match[2] ?? "").toLowerCase();
    if (suffix === "m" || suffix === "million") val *= 1_000_000;
    else if (suffix === "b" || suffix === "billion") val *= 1_000_000_000;
    else if (suffix === "k" || suffix === "thousand") val *= 1_000;
    amounts.push(val);
  }
  return amounts.length ? Math.max(...amounts) : null;
}

function parseTenderDate(dateStr: string): Date | null {
  if (!dateStr) return null;
  const noNote = dateStr.replace(/\s*\(estimated[^)]*\)/i, "").trim();
  const dateOnly = noNote.replace(/\s+at\s+\d+:\d+\s*[APap][Mm]/i, "").trim();
  const d = new Date(dateOnly);
  return isNaN(d.getTime()) ? null : d;
}

function nextBusinessDay(d: Date): Date {
  const result = new Date(d);
  const day = result.getDay();
  if (day === 6) result.setDate(result.getDate() + 2);
  else if (day === 0) result.setDate(result.getDate() + 1);
  return result;
}

function computeStartDate(bidOpenDateStr: string, days: number): string | null {
  const base = parseTenderDate(bidOpenDateStr);
  if (!base) return null;
  const result = nextBusinessDay(new Date(base.getTime() + days * 86_400_000));
  const formatted = result.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  return `${formatted} (estimated — ${days} calendar days from Bid open date)`;
}

function FieldConfidenceBadge(_props: { confidence?: number }) {
  // Confidence scoring disabled — grounding penalties didn't reflect actual
  // extraction correctness, so the badge was more misleading than useful.
  return null;
}

function SpecFieldsItemsList({
  items,
  extractionType,
}: {
  items: SummarySectionBlock[];
  extractionType?: string;
}) {
  if (!items?.length) return null;
  return (
    <SummaryContentBox>
      <ul className="divide-y divide-surface-border/80">
        {items.map((item, i) => (
          <li key={i} className="py-3 first:pt-0 last:pb-0">
            <SpecFieldRow
              item={item}
              extractionType={extractionType}
              valueAsSubtext={Boolean(item.date && !item.text?.includes(": "))}
              confidenceBadge={<FieldConfidenceBadge confidence={item.confidence} />}
            />
          </li>
        ))}
      </ul>
    </SummaryContentBox>
  );
}

function SectionPanel({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-surface-border last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-3 text-left text-sm font-semibold"
      >
        {title}
        <span className="text-ink-muted">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="pb-4 text-sm">{children}</div>}
    </div>
  );
}

function EmptySection() {
  return <p className="text-sm italic text-ink-muted">{NOT_FOUND}</p>;
}

function ProjectValueInputRow({
  onCalculate,
}: {
  onCalculate: (rawInput: string) => void;
}) {
  const [input, setInput] = useState("");

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-ink">
          Project value{" "}
          <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-700">
            Not in document
          </span>
        </span>
        <p className="text-xs text-ink-muted">
          Enter the value or range to calculate the estimated project start date.
        </p>
        <div className="mt-1 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. $1,200,000 or $500K–$1.5M"
            className="flex-1 rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            type="button"
            disabled={!input.trim()}
            onClick={() => onCalculate(input)}
            className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 hover:bg-accent/90 transition-colors"
          >
            Calculate start date
          </button>
        </div>
      </div>
    </li>
  );
}

function SpecDatesList({
  dates,
  showAwaitingNote,
}: {
  dates: SummarySectionBlock[];
  showAwaitingNote: boolean;
}) {
  if (!dates.length) return null;
  return (
    <SummaryContentBox>
      <ul className="divide-y divide-surface-border/80">
        {dates.map((item, i) => {
          if (item._calculated) {
            return (
              <li key={i} className="py-3 first:pt-0 last:pb-0">
                <div className="flex items-start gap-2.5">
                  <span className="w-5 shrink-0 pt-0.5 text-right text-xs font-medium tabular-nums text-ink-muted">
                    {i + 1}.
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm">
                        <span className="font-semibold">{item.text ?? "—"}:</span>
                      </p>
                      <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">
                        estimated
                      </span>
                      <FieldConfidenceBadge confidence={item.confidence} />
                    </div>
                    {item.date ? (
                      <p className="mt-1 text-sm font-normal leading-relaxed text-ink-muted">
                        {item.date}
                      </p>
                    ) : null}
                    {item._awaiting_project_value && showAwaitingNote && (
                      <p className="mt-1 text-xs italic text-amber-600">
                        Enter project value above to refine this estimate.
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          }
          return (
            <DeadlineItemRow
              key={i}
              item={item}
              index={i}
              showSources
              confidenceBadge={<FieldConfidenceBadge confidence={item.confidence} />}
            />
          );
        })}
      </ul>
    </SummaryContentBox>
  );
}

export function SummaryViewer({ data }: { data: GeneratedSummaryData }) {
  const spec = data.spec_check_fields;

  const [dates, setDates] = useState<SummarySectionBlock[]>(
    spec?.project_dates ?? []
  );

  const metadataItems = useMemo(
    () => sortMetadataItems(spec?.project_metadata_items ?? []),
    [spec?.project_metadata_items]
  );

  const hasSpec = Boolean(
    metadataItems.length ||
      spec?.project_people_items?.length ||
      spec?.project_size_location_items?.length ||
      dates.length ||
      spec?.bond_items?.length ||
      spec?.set_aside_items?.length
  );

  const docHasProjectValue = metadataItems.some((m) =>
    m.field_key === "project_value" ||
    (m.text ?? "").toLowerCase().includes("project value")
  );

  const bidOpenEntry = dates.find(
    (d) => (d.text ?? "").toLowerCase() === "bid open date"
  );

  const handleCalculate = useCallback(
    (rawInput: string) => {
      if (!bidOpenEntry?.date) return;
      const amount = parseDollarAmount(rawInput);
      const days = amount !== null && amount > 1_000_000 ? 60 : 30;
      const newDate = computeStartDate(bidOpenEntry.date, days);
      if (!newDate) return;
      setDates((prev) =>
        prev.map((d) =>
          d.text === "Project start date"
            ? {
                ...d,
                date: newDate,
                _days_offset: days,
                _awaiting_project_value: false,
              }
            : d
        )
      );
    },
    [bidOpenEntry]
  );

  if (!hasSpec) {
    return (
      <div className="rounded-lg border border-surface-border bg-surface px-5 py-4">
        <EmptySection />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface px-5">
      <SectionPanel title="Project overview" defaultOpen>
        <SummaryContentBox>
          <ul className="divide-y divide-surface-border/80">
            {metadataItems.map((item, i) => (
              <li key={i} className="py-3 first:pt-0 last:pb-0">
                <SpecFieldRow
                  item={item}
                  extractionType="eligibility_criteria"
                  confidenceBadge={<FieldConfidenceBadge confidence={item.confidence} />}
                />
              </li>
            ))}
            {!docHasProjectValue && (
              <ProjectValueInputRow onCalculate={handleCalculate} />
            )}
          </ul>
        </SummaryContentBox>
      </SectionPanel>

      <SectionPanel title="People (engineer / architect)" defaultOpen={false}>
        {spec?.project_people_items?.length ? (
          <SpecFieldsItemsList items={spec.project_people_items!} extractionType="eligibility_criteria" />
        ) : (
          <EmptySection />
        )}
      </SectionPanel>

      <SectionPanel title="Size & location" defaultOpen={false}>
        {spec?.project_size_location_items?.length ? (
          <SpecFieldsItemsList items={spec.project_size_location_items!} extractionType="technical_requirements" />
        ) : (
          <EmptySection />
        )}
      </SectionPanel>

      <SectionPanel title="Important dates" defaultOpen={false}>
        {dates.length ? (
          <SpecDatesList
            dates={dates}
            showAwaitingNote={!docHasProjectValue}
          />
        ) : (
          <EmptySection />
        )}
      </SectionPanel>

      <SectionPanel title="Bond / security instruments" defaultOpen={false}>
        {spec?.bond_items?.length ? (
          <SpecFieldsItemsList items={spec.bond_items!} extractionType="penalties_and_risks" />
        ) : (
          <EmptySection />
        )}
      </SectionPanel>

      {spec?.set_aside_items?.length ? (
        <SectionPanel title="Set-asides / diversity goals" defaultOpen={false}>
          <SpecFieldsItemsList items={spec.set_aside_items!} extractionType="set_asides" />
        </SectionPanel>
      ) : null}
    </div>
  );
}
