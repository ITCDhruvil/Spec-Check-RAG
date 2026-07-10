import type { SourceCitation } from "@/lib/types/intelligence";

export type DeadlineDisplay = {
  label: string;
  value?: string;
};

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
