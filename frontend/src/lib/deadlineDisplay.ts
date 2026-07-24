import type { SourceCitation } from "@/lib/types/intelligence";

export type DeadlineDisplay = {
  label: string;
  value?: string;
};

/**
 * Format an ISO date(-time) as a clean 12-hour display:
 * "March 11, 2026, 10:00 AM" (date-only values omit the time).
 * Returns undefined when the input is not a parseable ISO date.
 */
export function formatDeadlineDate(iso?: string | null): string | undefined {
  const raw = (iso ?? "").trim();
  if (!raw || !/^\d{4}-\d{2}-\d{2}/.test(raw)) return undefined;
  // Date-only strings parse as UTC midnight and can shift a day in local
  // time — append a local noon time so the calendar date is stable.
  const hasTimeComponent = /T\d{2}:\d{2}/.test(raw);
  const d = new Date(hasTimeComponent ? raw : `${raw.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return undefined;

  const datePart = d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  // Date-only ISO strings ("2026-03-11") carry no meaningful time.
  if (!hasTimeComponent) return datePart;

  const timePart = d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  return `${datePart}, ${timePart}`;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Pull "Label: value" from a citation line (same text users see in citations). */
export function extractValueAfterLabel(
  sourceText: string,
  label: string,
): string | undefined {
  const src = sourceText.trim();
  const tag = label.trim();
  if (!src || !tag) return undefined;

  const atStart = new RegExp(
    `^${escapeRegex(tag)}\\s*[:\\-–]\\s*(.+)$`,
    "i",
  );
  const m = src.match(atStart);
  if (m?.[1]) return m[1].trim();

  const idx = src.toLowerCase().indexOf(tag.toLowerCase());
  if (idx >= 0) {
    let rest = src.slice(idx + tag.length).trim();
    if (/^[:\\-–]/.test(rest)) rest = rest.replace(/^[:\\-–]\s*/, "").trim();
    if (rest) return rest;
  }

  return undefined;
}

function firstSourceText(sources?: SourceCitation[]): string | undefined {
  const t = sources?.[0]?.source_text?.trim();
  return t || undefined;
}

/**
 * Resolve label + value for deadline rows (briefing + insights).
 * Prefers citation source_text so date, time, and URLs match the document.
 */
export function resolveDeadlineDisplay(input: {
  text?: string;
  item?: string;
  date?: string | null;
  date_time?: string | null;
  value?: string | null;
  requirement?: string;
  sourceText?: string;
  sources?: SourceCitation[];
}): DeadlineDisplay {
  const label = (input.text || input.item || "").trim();
  const req = (input.requirement || "").trim();
  const sourceText =
    input.sourceText?.trim() || firstSourceText(input.sources) || "";
  const structured =
    (input.date_time || input.value || input.date || "").trim() || undefined;

  const tag =
    label ||
    (req.includes(":") ? req.slice(0, req.indexOf(":")).trim() : "") ||
    req;

  // Parsed ISO date wins: clean, consistent 12-hour display.
  // Raw document phrasing stays available in the citation panel.
  const formatted =
    formatDeadlineDate(input.date) ?? formatDeadlineDate(input.date_time);
  if (formatted && tag) {
    return { label: tag, value: formatted };
  }

  if (sourceText && tag) {
    const fromSource = extractValueAfterLabel(sourceText, tag);
    if (fromSource) {
      return { label: tag, value: fromSource };
    }
  }

  if (req.includes(":")) {
    const colon = req.indexOf(":");
    const reqLabel = req.slice(0, colon).trim();
    const reqValue = req.slice(colon + 1).trim();
    if (reqValue) {
      return { label: reqLabel || tag || "Deadline", value: reqValue };
    }
  }

  if (tag && structured) {
    const merged =
      structured && tag && !structured.toLowerCase().includes(tag.toLowerCase())
        ? structured
        : structured;
    return { label: tag, value: merged };
  }

  if (tag && req && req !== tag) {
    return { label: tag, value: req };
  }

  if (sourceText && !tag) {
    return { label: "Deadline", value: sourceText };
  }

  return { label: tag || req || "—", value: structured };
}

/** US RFPs rarely say "pre-bid" — same event as Proposer's / Pre-Proposal Conference. */
export function deadlineDisplayLabel(label: string): string {
  const lower = label.toLowerCase();
  if (lower.includes("proposer") && lower.includes("conference")) {
    return "Pre-bid conference (Proposer's Conference)";
  }
  if (lower.includes("pre-proposal") || lower.includes("preproposal")) {
    return "Pre-bid conference (Pre-Proposal Conference)";
  }
  if (lower.includes("bidder") && lower.includes("conference")) {
    return "Pre-bid conference (Bidder Conference)";
  }
  if (lower.includes("advertised") || lower === "issue date for rfp") {
    return "RFP issue / advertised date";
  }
  return label;
}
