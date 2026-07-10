import type { ExtractedInsight } from "@/lib/types/intelligence";

/** Display order and grouping for extracted insights. */
export const INSIGHT_GROUP_ORDER: {
  id: string;
  label: string;
  types: string[];
}[] = [
  {
    id: "qualification",
    label: "Qualification & evaluation",
    types: ["eligibility_criteria", "evaluation_criteria"],
  },
  {
    id: "commercial",
    label: "Commercial & risk",
    types: ["payment_terms", "penalties_and_risks"],
  },
  {
    id: "technical",
    label: "Technical & delivery",
    types: ["technical_requirements", "scope_of_work"],
  },
  {
    id: "submission",
    label: "Submission package",
    types: ["mandatory_documents", "submission_deadlines"],
  },
];

export const INSIGHT_TYPE_LABELS: Record<string, string> = {
  eligibility_criteria: "Eligibility Criteria",
  submission_deadlines: "Submission Deadlines",
  technical_requirements: "Technical Requirements",
  scope_of_work: "Scope of Work",
  payment_terms: "Payment Terms",
  penalties_and_risks: "Penalties & Risks",
  mandatory_documents: "Mandatory Documents",
  evaluation_criteria: "Evaluation Criteria",
};

const TYPE_ORDER = INSIGHT_GROUP_ORDER.flatMap((g) => g.types);

const LARGE_LIST_THRESHOLD = 12;
const INITIAL_VISIBLE = 8;

export function sortInsights(insights: ExtractedInsight[]): ExtractedInsight[] {
  const index = new Map(TYPE_ORDER.map((t, i) => [t, i]));
  return [...insights].sort(
    (a, b) =>
      (index.get(a.extraction_type) ?? 99) -
      (index.get(b.extraction_type) ?? 99)
  );
}

export function groupInsightsByPhase(
  insights: ExtractedInsight[]
): { groupLabel: string; insights: ExtractedInsight[] }[] {
  const byType = new Map(insights.map((i) => [i.extraction_type, i]));
  const result: { groupLabel: string; insights: ExtractedInsight[] }[] = [];

  for (const group of INSIGHT_GROUP_ORDER) {
    const members = group.types
      .map((t) => byType.get(t))
      .filter((i): i is ExtractedInsight => Boolean(i));
    if (members.length) {
      result.push({ groupLabel: group.label, insights: members });
    }
  }

  const known = new Set(TYPE_ORDER);
  const orphan = insights.filter((i) => !known.has(i.extraction_type));
  if (orphan.length) {
    result.push({ groupLabel: "Other", insights: orphan });
  }

  return result;
}

export function confidenceTone(score: number): "strong" | "moderate" | "weak" {
  const pct = score * 100;
  if (pct >= 85) return "strong";
  if (pct >= 70) return "moderate";
  return "weak";
}

export function isLargeInsight(insight: ExtractedInsight): boolean {
  return (insight.item_count ?? insight.payload.items?.length ?? 0) >
    LARGE_LIST_THRESHOLD;
}

export { INITIAL_VISIBLE, LARGE_LIST_THRESHOLD };
