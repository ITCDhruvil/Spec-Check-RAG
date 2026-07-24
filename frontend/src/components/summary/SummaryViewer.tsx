"use client";

import { useState, useCallback, useMemo } from "react";

import { SummaryContentBox } from "@/components/summary/SummaryContentBox";
import { EventsBlock, SpecFieldRow } from "@/components/summary/SpecFieldRow";
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
  canonicalFields,
}: {
  items: SummarySectionBlock[];
  extractionType?: string;
  /** Fields that must always be shown; absent ones render "Not found in
   * document" with tick/wrong feedback so the user can verify or correct. */
  canonicalFields?: { key: string; label: string }[];
}) {
  const allItems = canonicalFields
    ? withMissingFieldPlaceholders(items ?? [], canonicalFields)
    : items ?? [];
  if (!allItems.length) return null;
  return (
    <SummaryContentBox>
      <ul className="divide-y divide-surface-border/80">
        {allItems.map((item, i) => (
          <li key={i} className="py-3 first:pt-0 last:pb-0">
            <SpecFieldRow
              item={item}
              extractionType={extractionType}
              notFound={Boolean(item._not_found)}
              valueAsSubtext={Boolean(item.date && !item.text?.includes(": "))}
              confidenceBadge={
                item._not_found ? undefined : (
                  <FieldConfidenceBadge confidence={item.confidence} />
                )
              }
            />
          </li>
        ))}
      </ul>
    </SummaryContentBox>
  );
}

/** Append placeholder rows for canonical fields missing from the extraction. */
function withMissingFieldPlaceholders(
  items: SummarySectionBlock[],
  canonical: { key: string; label: string }[]
): SummarySectionBlock[] {
  const present = new Set(items.map((d) => d.field_key ?? "").filter(Boolean));
  const placeholders = canonical
    .filter((f) => !present.has(f.key))
    .map(
      (f): SummarySectionBlock => ({
        text: f.label,
        field_key: f.key,
        _not_found: true,
      })
    );
  return [...items, ...placeholders];
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
          <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
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

/** Canonical fields per section — always shown; absent ones render
 * "Not found in document" with tick/wrong feedback. */
const METADATA_FIELDS: { key: string; label: string }[] = [
  { key: "project_name", label: "Project name" },
  { key: "project_solicitation_number", label: "Project solicitation number" },
  { key: "project_owner", label: "Project owner" },
  { key: "project_sector", label: "Project sector" },
  { key: "project_value", label: "Project value" },
  { key: "project_document_acquisition_note", label: "Project document acquisition note" },
  { key: "project_description", label: "Project description" },
];

const PEOPLE_FIELDS: { key: string; label: string }[] = [
  { key: "project_engineer", label: "Project engineer" },
  { key: "project_architect", label: "Project architect" },
];

const SIZE_LOCATION_FIELDS: { key: string; label: string }[] = [
  { key: "project_location", label: "Project location" },
  { key: "project_square_footage", label: "Project square footage" },
];

const BOND_FIELDS: { key: string; label: string }[] = [
  { key: "bid_bond_information", label: "Bid bond information" },
  { key: "payment_and_security_bond", label: "Performance & payment bond" },
  { key: "maintenance_and_labor_bond", label: "Maintenance & labor bond" },
  { key: "certified_checks", label: "Certified checks" },
  { key: "other_bonds", label: "Other bonds" },
];

const SET_ASIDE_FIELDS: { key: string; label: string }[] = [
  { key: "set_aside", label: "Set-aside" },
];

/** Canonical date fields — always shown; absent values render "Not found in document". */
const CANONICAL_DATE_FIELDS: { key: string; label: string }[] = [
  { key: "bid_deadline_date_time", label: "Bid deadline" },
  { key: "bid_open_date_time", label: "Bid open date" },
  { key: "pre_bid_deadline_date_time", label: "Pre-bid deadline" },
  { key: "question_deadline_date_time", label: "Question deadline" },
  { key: "site_visit_date_time", label: "Site visit" },
  { key: "municipal_meeting_date_time", label: "Award date" },
  { key: "project_start_date_time", label: "Project start date" },
  { key: "project_end_date_time", label: "Project end date" },
];

function withMissingDatePlaceholders(
  dates: SummarySectionBlock[]
): SummarySectionBlock[] {
  const present = new Set(
    dates.map((d) => d.field_key ?? "").filter(Boolean)
  );
  const presentLabels = new Set(
    dates.map((d) => (d.text ?? "").trim().toLowerCase())
  );
  const placeholders = CANONICAL_DATE_FIELDS.filter(
    (f) =>
      !present.has(f.key) && !presentLabels.has(f.label.toLowerCase())
  ).map(
    (f): SummarySectionBlock => ({
      text: f.label,
      field_key: f.key,
      _not_found: true,
    })
  );
  return [...dates, ...placeholders];
}

function SpecDatesList({
  dates,
  showAwaitingNote,
}: {
  dates: SummarySectionBlock[];
  showAwaitingNote: boolean;
}) {
  const allDates = withMissingDatePlaceholders(dates);
  return (
    <SummaryContentBox>
      <ul className="divide-y divide-surface-border/80">
        {allDates.map((item, i) => {
          if (item._not_found) {
            // Feedback stays available: the user can confirm the field is
            // truly absent, or mark it wrong and supply the real value.
            return (
              <li key={i} className="py-3 first:pt-0 last:pb-0">
                <SpecFieldRow
                  item={item}
                  extractionType="submission_deadlines"
                  notFound
                />
              </li>
            );
          }
          if (item._calculated) {
            // Split "April 10, 2026 (estimated — 30 calendar days from Bid
            // open date)" into a clean value + a muted derivation footnote.
            const raw = String(item.date ?? "");
            const parenIdx = raw.indexOf("(");
            const cleanDate = (parenIdx > 0 ? raw.slice(0, parenIdx) : raw).trim();
            const derivation =
              parenIdx > 0 ? raw.slice(parenIdx + 1).replace(/\)\s*$/, "") : "";
            return (
              <li key={i} className="py-3 first:pt-0 last:pb-0">
                <SpecFieldRow
                  item={{ ...item, date: cleanDate }}
                  extractionType="submission_deadlines"
                  valueAsSubtext={Boolean(cleanDate)}
                  confidenceBadge={<FieldConfidenceBadge confidence={item.confidence} />}
                  valueBadge={
                    <span className="ml-1.5 rounded bg-accent/10 px-1.5 py-0.5 text-xs font-medium text-accent">
                      estimated
                    </span>
                  }
                  footnote={
                    <>
                      {derivation && (
                        <p className="mt-0.5 text-xs text-ink-muted">{derivation}</p>
                      )}
                      {item._awaiting_project_value && showAwaitingNote && (
                        <p className="mt-0.5 text-xs italic text-amber-600">
                          Enter project value above to refine this estimate.
                        </p>
                      )}
                    </>
                  }
                />
              </li>
            );
          }
          // SpecFieldRow brings copy / jump / feedback / citations — the same
          // actions every other section already has.
          return (
            <li key={i} className="py-3 first:pt-0 last:pb-0">
              <SpecFieldRow
                item={item}
                extractionType="submission_deadlines"
                valueAsSubtext={Boolean(item.date)}
                confidenceBadge={<FieldConfidenceBadge confidence={item.confidence} />}
                labelBadge={
                  // Only the disqualification-critical case gets a badge;
                  // non-mandatory is already stated in the Events text.
                  item._mandatory === true ? (
                    <span className="mr-1 rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-500/10 dark:text-red-300">
                      Mandatory
                    </span>
                  ) : undefined
                }
                footnote={
                  item._note ? (
                    <EventsBlock
                      fieldKey={item.field_key ?? "date"}
                      text={item._note}
                      sources={item._note_sources}
                    />
                  ) : null
                }
              />
            </li>
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
            {withMissingFieldPlaceholders(metadataItems, METADATA_FIELDS).map(
              (item, i) => (
                <li key={i} className="py-3 first:pt-0 last:pb-0">
                  <SpecFieldRow
                    item={item}
                    extractionType="eligibility_criteria"
                    notFound={Boolean(item._not_found)}
                    confidenceBadge={
                      item._not_found ? undefined : (
                        <FieldConfidenceBadge confidence={item.confidence} />
                      )
                    }
                  />
                </li>
              )
            )}
            {!docHasProjectValue && (
              <ProjectValueInputRow onCalculate={handleCalculate} />
            )}
          </ul>
        </SummaryContentBox>
      </SectionPanel>

      <SectionPanel title="People (engineer / architect)" defaultOpen={false}>
        <SpecFieldsItemsList
          items={spec?.project_people_items ?? []}
          extractionType="eligibility_criteria"
          canonicalFields={PEOPLE_FIELDS}
        />
      </SectionPanel>

      <SectionPanel title="Size & location" defaultOpen={false}>
        <SpecFieldsItemsList
          items={spec?.project_size_location_items ?? []}
          extractionType="technical_requirements"
          canonicalFields={SIZE_LOCATION_FIELDS}
        />
      </SectionPanel>

      <SectionPanel title="Important dates" defaultOpen={false}>
        <SpecDatesList
          dates={dates}
          showAwaitingNote={!docHasProjectValue}
        />
      </SectionPanel>

      <SectionPanel title="Bond / security instruments" defaultOpen={false}>
        <SpecFieldsItemsList
          items={spec?.bond_items ?? []}
          extractionType="penalties_and_risks"
          canonicalFields={BOND_FIELDS}
        />
      </SectionPanel>

      <SectionPanel title="Set-asides / diversity goals" defaultOpen={false}>
        <SpecFieldsItemsList
          items={spec?.set_aside_items ?? []}
          extractionType="set_asides"
          canonicalFields={SET_ASIDE_FIELDS}
        />
      </SectionPanel>
    </div>
  );
}
