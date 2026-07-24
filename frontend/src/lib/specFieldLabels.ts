import { formatDeadlineDate } from "@/lib/deadlineDisplay";

/** Display labels mirroring backend spec_check_fields_registry FIELD_DEFS. */
export const SPEC_FIELD_LABELS: Record<string, string> = {
  project_name: "Project name",
  project_description: "Project description",
  project_owner: "Project owner",
  project_sector: "Project sector",
  project_solicitation_number: "Project solicitation number",
  project_document_acquisition_note: "Project document acquisition note",
  project_value: "Project value",
  project_engineer: "Project engineer",
  project_architect: "Project architect",
  project_square_footage: "Project square footage",
  project_location: "Project location",
  bid_bond_information: "Bid bond information",
  payment_and_security_bond: "Performance & payment bond",
  maintenance_and_labor_bond: "Maintenance & labor bond",
  certified_checks: "Certified checks",
  other_bonds: "Other bonds",
  bid_deadline_date_time: "Bid deadline",
  bid_open_date_time: "Bid open date",
  project_start_date_time: "Project start date",
  project_end_date_time: "Project end date",
  pre_bid_deadline_date_time: "Pre-bid deadline",
  site_visit_date_time: "Site visit",
  question_deadline_date_time: "Question deadline",
  municipal_meeting_date_time: "Award date",
  // Single common set-aside field; legacy per-program keys kept for old summaries.
  set_aside: "Set-aside",
  set_aside_mbe: "MBE",
  set_aside_wbe: "WBE",
  set_aside_dbe: "DBE",
  set_aside_dvbe: "DVBE",
  set_aside_hub: "HUB",
  set_aside_sbe: "SBE",
};

export const METADATA_FIELD_ORDER = [
  "project_name",
  "project_solicitation_number",
  "project_owner",
  "project_sector",
  "project_value",
  "project_document_acquisition_note",
  "project_description",
] as const;

export function resolveFieldLabel(
  item: { field_key?: string; text?: string; item?: string },
  fallbackLabel?: string
): string {
  if (item.field_key && SPEC_FIELD_LABELS[item.field_key]) {
    return SPEC_FIELD_LABELS[item.field_key];
  }
  const raw = (item.text ?? item.item ?? "").trim();
  if (raw.includes(": ")) {
    return raw.split(": ", 2)[0]?.trim() || fallbackLabel || "Field";
  }
  return (fallbackLabel ?? raw) || "Field";
}

export function resolveFieldValue(
  item: { field_key?: string; text?: string; item?: string; date?: string | null },
  useDateAsValue = false
): string {
  if (useDateAsValue && item.date) {
    return formatDeadlineDate(item.date) ?? String(item.date);
  }
  const raw = (item.text ?? item.item ?? "").trim();
  if (raw.includes(": ")) {
    // Strip the "Label: " prefix only when it actually is the field's label —
    // values like "MBE: 10% participation goal" must keep their own colon text.
    const [prefix, rest] = [
      raw.split(": ", 2)[0]?.trim() ?? "",
      raw.slice(raw.indexOf(": ") + 2).trim(),
    ];
    const knownLabel = item.field_key ? SPEC_FIELD_LABELS[item.field_key] : undefined;
    if (!knownLabel || prefix.toLowerCase() === knownLabel.toLowerCase()) {
      return rest || raw;
    }
    return raw;
  }
  return raw;
}

export function sortMetadataItems<T extends { field_key?: string }>(items: T[]): T[] {
  const order = METADATA_FIELD_ORDER;
  return [...items].sort((a, b) => {
    const ai = order.indexOf(a.field_key as (typeof order)[number]);
    const bi = order.indexOf(b.field_key as (typeof order)[number]);
    const aIdx = ai === -1 ? order.length : ai;
    const bIdx = bi === -1 ? order.length : bi;
    return aIdx - bIdx;
  });
}
