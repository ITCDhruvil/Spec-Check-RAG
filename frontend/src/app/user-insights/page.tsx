"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  BarElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

import { RefreshIcon, XMarkIcon } from "@/components/ui/icons";
import { Spokes, SpokesLoader } from "@/components/ui/Spokes";
import {
  fetchAIInsights,
  fetchUserInsightDetail,
  fetchUserInsights,
  type UserInsightRow,
} from "@/lib/api/insights";
import { TextShimmer } from "@/components/ui/TextShimmer";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { useAuth } from "@/providers/auth-provider";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
  Filler
);

const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 0, label: "All time" },
];

const ACCENT = "#2563eb";
const AMBER = "#d97706";

function fmtSeconds(s: number | null): string {
  if (s == null) return "—";
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "bad" }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface p-4">
      <p className={`text-2xl font-semibold tabular-nums ${tone === "bad" ? "text-red-600" : ""}`}>
        {value}
      </p>
      <p className="mt-0.5 text-xs uppercase tracking-wide text-ink-muted">{label}</p>
    </div>
  );
}

/** Auto-generated plain-language observations from the current data. */
function buildInsightNotes(users: UserInsightRow[]): string[] {
  const notes: string[] = [];
  const active = users.filter((u) => u.docs_total > 0);
  if (!active.length) return notes;

  const top = [...active].sort((a, b) => b.docs_completed - a.docs_completed)[0];
  if (top.docs_completed > 0) {
    notes.push(
      `${top.username} processed the most documents (${top.docs_completed} completed).`
    );
  }

  const withFields = active.filter((u) => u.fields_extracted >= 20);
  if (withFields.length) {
    const best = [...withFields].sort((a, b) => a.correction_rate - b.correction_rate)[0];
    notes.push(
      `${best.username} has the best accuracy — only ${best.correction_rate}% of ${best.fields_extracted} extracted fields needed correction.`
    );
    const worst = [...withFields].sort((a, b) => b.correction_rate - a.correction_rate)[0];
    if (worst.user_id !== best.user_id && worst.correction_rate >= 5) {
      notes.push(
        `${worst.username}'s documents show the highest correction rate (${worst.correction_rate}%) — worth reviewing which fields fail there.`
      );
    }
  }

  const failing = active.filter((u) => u.docs_failed > 0);
  if (failing.length) {
    const f = [...failing].sort((a, b) => b.docs_failed - a.docs_failed)[0];
    notes.push(`${f.username} hit ${f.docs_failed} failed document(s) — check failure reasons below.`);
  }

  const timed = active.filter((u) => u.avg_processing_seconds != null && u.avg_processing_seconds < 86_400);
  if (timed.length) {
    const fastest = [...timed].sort(
      (a, b) => (a.avg_processing_seconds ?? 0) - (b.avg_processing_seconds ?? 0)
    )[0];
    notes.push(
      `Fastest average processing: ${fastest.username} at ${fmtSeconds(fastest.avg_processing_seconds)} per document.`
    );
  }

  // Team-level facts
  const totalFields = active.reduce((s, u) => s + u.fields_extracted, 0);
  const totalCorrected = active.reduce((s, u) => s + u.fields_corrected, 0);
  const totalConfirmed = active.reduce((s, u) => s + u.fields_confirmed, 0);
  if (totalFields) {
    notes.push(
      `Team extracted ${totalFields.toLocaleString()} fields with an overall correction rate of ${(
        (totalCorrected / totalFields) * 100
      ).toFixed(1)}%.`
    );
  }
  if (totalConfirmed) {
    notes.push(`${totalConfirmed} field(s) explicitly confirmed correct by reviewers.`);
  }
  const completedTotal = active.reduce((s, u) => s + u.docs_completed, 0);
  const docsTotal = active.reduce((s, u) => s + u.docs_total, 0);
  if (docsTotal) {
    notes.push(
      `${completedTotal} of ${docsTotal} documents completed successfully (${Math.round(
        (completedTotal / docsTotal) * 100
      )}%).`
    );
  }
  return notes.slice(0, 5);
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
  wide,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className={`max-h-[80vh] w-full ${wide ? "max-w-3xl" : "max-w-xl"} overflow-hidden rounded-lg border border-surface-border bg-surface shadow-xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-surface-border px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold">{title}</h3>
            {subtitle && <p className="text-xs text-ink-muted">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-ink-muted hover:bg-surface-muted hover:text-ink"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[calc(80vh-52px)] overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

type DrillKind = "docs" | "completed" | "failed" | "fields" | "corrected";

const DOCS_PER_PAGE = 6;

function KeyValueGrid({ rows }: { rows: { field: string; count: number }[] }) {
  if (!rows.length) {
    return <p className="py-6 text-center text-sm text-ink-muted">Nothing in this period.</p>;
  }
  return (
    <div className={rows.length > 10 ? "columns-2 gap-6 sm:columns-3" : ""}>
      {rows.map((row) => (
        <div
          key={row.field}
          className="mb-1.5 flex break-inside-avoid items-center justify-between gap-3 text-sm"
        >
          <span className="truncate font-mono text-xs" title={row.field}>
            {row.field}
          </span>
          <span className="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-xs font-semibold tabular-nums">
            {row.count}
          </span>
        </div>
      ))}
    </div>
  );
}

function DrillDownModal({
  user,
  kind,
  days,
  onClose,
}: {
  user: UserInsightRow;
  kind: DrillKind;
  days: number;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [docFilter, setDocFilter] = useState<string>("all");

  const query = useQuery({
    queryKey: ["user-insight-detail", user.user_id, days],
    queryFn: () => fetchUserInsightDetail(user.user_id, days),
  });

  const titles: Record<DrillKind, string> = {
    docs: "Documents",
    completed: "Completed documents",
    failed: "Failed documents",
    fields: "Extracted fields",
    corrected: "Corrected fields",
  };

  const d = query.data;
  const isDocList = kind === "docs" || kind === "completed" || kind === "failed";

  const docs = useMemo(() => {
    const all = d?.documents ?? [];
    if (kind === "completed") return all.filter((x) => x.status === "completed");
    if (kind === "failed") return all.filter((x) => x.status === "failed");
    return all;
  }, [d, kind]);

  const totalPages = Math.max(1, Math.ceil(docs.length / DOCS_PER_PAGE));
  const pageDocs = docs.slice((page - 1) * DOCS_PER_PAGE, page * DOCS_PER_PAGE);

  const correctedRows = useMemo(() => {
    if (kind !== "corrected" || !d) return [];
    if (docFilter === "all") return d.corrected;
    return (
      d.corrected_by_document.find((x) => x.document_id === docFilter)?.fields ?? []
    );
  }, [d, kind, docFilter]);

  return (
    <Modal
      title={`${titles[kind]} — ${user.username}`}
      subtitle={user.email}
      onClose={onClose}
      wide={kind === "fields" || kind === "corrected"}
    >
      {query.isPending && <SpokesLoader className="py-8" />}
      {query.isError && (
        <p className="py-6 text-center text-sm text-red-600">
          {(query.error as Error).message}
        </p>
      )}

      {d && isDocList && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-muted">
                <th className="py-2">Document</th>
                <th className="py-2 text-right">Size</th>
                <th className="py-2 text-right">Status</th>
                <th className="py-2 text-right">Uploaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/70">
              {pageDocs.map((doc) => (
                <tr key={doc.id}>
                  <td className="max-w-[280px] truncate py-2 pr-3" title={doc.filename}>
                    {doc.filename}
                  </td>
                  <td className="py-2 text-right tabular-nums">{doc.size_mb} MB</td>
                  <td className="py-2 text-right">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        doc.status === "completed"
                          ? "bg-green-100 text-green-800 dark:bg-emerald-500/15 dark:text-emerald-300"
                          : doc.status === "failed"
                            ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300"
                            : "bg-surface-muted text-ink-muted"
                      }`}
                    >
                      {doc.status}
                    </span>
                  </td>
                  <td className="py-2 text-right text-xs text-ink-muted">
                    {fmtDate(doc.created_at)}
                  </td>
                </tr>
              ))}
              {!docs.length && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-ink-muted">
                    No documents in this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {docs.length > DOCS_PER_PAGE && (
            <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-3 text-xs text-ink-muted">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded px-2.5 py-1 hover:bg-surface-muted disabled:opacity-40"
              >
                Prev
              </button>
              <span>
                Page {page} of {totalPages} · {docs.length} documents
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="rounded px-2.5 py-1 hover:bg-surface-muted disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {d && kind === "fields" && <KeyValueGrid rows={d.fields} />}

      {d && kind === "corrected" && (
        <>
          {d.corrected_by_document.length > 0 && (
            <div className="mb-4 flex items-center gap-2">
              <label className="text-xs text-ink-muted">Document:</label>
              <select
                value={docFilter}
                onChange={(e) => setDocFilter(e.target.value)}
                className="max-w-[320px] truncate rounded border border-surface-border bg-surface px-2 py-1 text-xs"
              >
                <option value="all">All documents</option>
                {d.corrected_by_document.map((doc) => (
                  <option key={doc.document_id} value={doc.document_id}>
                    {doc.filename}
                  </option>
                ))}
              </select>
            </div>
          )}
          <KeyValueGrid rows={correctedRows} />
        </>
      )}
    </Modal>
  );
}

function CountButton({
  value,
  onClick,
  tone,
}: {
  value: number;
  onClick: () => void;
  tone?: "bad";
}) {
  if (!value) return <span className="text-ink-muted">0</span>;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-1.5 py-0.5 font-medium underline-offset-2 transition-colors hover:underline ${
        tone === "bad" ? "text-red-600" : "text-accent"
      }`}
    >
      {value}
    </button>
  );
}

export default function UserInsightsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [days, setDays] = useState(30);
  const [drill, setDrill] = useState<{ user: UserInsightRow; kind: DrillKind } | null>(null);

  // Page header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "User Insights",
    subtitle: "Team processing activity and accuracy signals",
  });

  useEffect(() => {
    if (!loading && user && !user.is_management) {
      router.replace("/");
    }
  }, [user, loading, router]);

  const query = useQuery({
    queryKey: ["user-insights", days],
    queryFn: () => fetchUserInsights(days),
    enabled: Boolean(user?.is_management),
  });

  const aiQuery = useQuery({
    queryKey: ["ai-insights", days],
    queryFn: () => fetchAIInsights(days),
    enabled: Boolean(user?.is_management),
    staleTime: 5 * 60 * 1000,
  });

  const data = query.data;

  const notes = useMemo(() => (data ? buildInsightNotes(data.users) : []), [data]);

  const uploadsChart = useMemo(() => {
    const t = data?.activity_timeline ?? [];
    return {
      labels: t.map((p) => fmtDay(p.date)),
      datasets: [
        {
          label: "Uploads",
          data: t.map((p) => p.uploads),
          backgroundColor: ACCENT,
          borderRadius: 2,
          maxBarThickness: 28,
        },
      ],
    };
  }, [data]);

  const trendChart = useMemo(() => {
    const t = data?.accuracy_trend ?? [];
    return {
      labels: t.map((p) => fmtDay(p.date)),
      datasets: [
        {
          label: "Correction rate %",
          data: t.map((p) => p.correction_rate),
          borderColor: AMBER,
          borderWidth: 2,
          fill: false,
          tension: 0,
          pointRadius: 2.5,
          pointBackgroundColor: AMBER,
        },
      ],
    };
  }, [data]);

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { intersect: false },
    },
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 10 } } },
      y: {
        beginAtZero: true,
        border: { display: false },
        grid: { color: "rgba(0,0,0,0.05)" },
        ticks: { font: { size: 10 }, precision: 0, maxTicksLimit: 5 },
      },
    },
  };

  if (loading || !user?.is_management) {
    return loading ? (
      <SpokesLoader className="py-24" />
    ) : (
      <div className="py-12 text-center text-ink-muted">Redirecting…</div>
    );
  }

  const totals = data?.users.reduce(
    (acc, u) => ({
      docs: acc.docs + u.docs_total,
      fields: acc.fields + u.fields_extracted,
      corrected: acc.corrected + u.fields_corrected,
    }),
    { docs: 0, fields: 0, corrected: 0 }
  );

  return (
    <div className="space-y-6">
      {query.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {(query.error as Error).message}
        </div>
      )}

      {query.isPending ? (
        <SpokesLoader label="Loading insights…" className="py-16" />
      ) : data ? (
        <>
          {/* Summary tiles */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Active users" value={String(data.users.length)} />
            <StatTile label="Documents" value={String(totals?.docs ?? 0)} />
            <StatTile label="Fields extracted" value={String(totals?.fields ?? 0)} />
            <StatTile label="Fields corrected" value={String(totals?.corrected ?? 0)} />
            <StatTile
              label="Failed documents"
              value={`${data.failure_stats.documents_failed} / ${data.failure_stats.documents_total}`}
              tone={data.failure_stats.documents_failed > 0 ? "bad" : undefined}
            />
          </div>

          {/* Highlights: deterministic facts left, AI analysis right */}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <h3 className="text-sm font-semibold">Highlights</h3>
              {notes.length ? (
                <ul className="mt-3 divide-y divide-surface-border/60">
                  {notes.slice(0, 5).map((n, i) => (
                    <li key={i} className="flex items-start gap-2.5 py-1.5 text-sm leading-relaxed text-ink first:pt-0 last:pb-0">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      {n}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-ink-muted">No activity in this period.</p>
              )}
            </div>

            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">AI analysis</h3>
                <button
                  type="button"
                  onClick={() =>
                    fetchAIInsights(days, true).then(() =>
                      aiQuery.refetch()
                    )
                  }
                  disabled={aiQuery.isFetching}
                  title="Re-run AI analysis"
                  className="flex h-7 w-7 items-center justify-center rounded text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink disabled:opacity-50"
                >
                  {aiQuery.isFetching ? (
                    <Spokes className="h-3.5 w-3.5" size={14} />
                  ) : (
                    <RefreshIcon className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
              {aiQuery.isPending ? (
                <p className="mt-2 text-sm">
                  <TextShimmer>Analyzing team data…</TextShimmer>
                </p>
              ) : aiQuery.isError ? (
                <p className="mt-2 text-sm text-ink-muted">
                  {(aiQuery.error as Error & { status?: number }).status === 403
                    ? "AI analysis is disabled for your role."
                    : "Analysis unavailable — try refresh."}
                </p>
              ) : !aiQuery.data?.insights.length ? (
                <p className="mt-2 text-sm text-ink-muted">
                  Not enough data for analysis in this period.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {aiQuery.data.insights.slice(0, 3).map((ins, i) => (
                    <li key={i} className="text-sm">
                      <p className="flex items-center gap-2 font-medium text-ink">
                        <span
                          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                            ins.kind === "problem"
                              ? "bg-red-500"
                              : ins.kind === "recommendation"
                                ? "bg-emerald-500"
                                : "bg-accent"
                          }`}
                        />
                        {ins.title}
                      </p>
                      <p className="mt-0.5 pl-3.5 text-xs leading-relaxed text-ink-muted">
                        {ins.detail}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Per-user table with period filter in header */}
          <div className="rounded-lg border border-surface-border bg-surface">
            <div className="flex items-center justify-between border-b border-surface-border px-5 py-2.5">
              <h3 className="text-sm font-semibold">Per-user activity</h3>
              <div className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p.days}
                    type="button"
                    onClick={() => setDays(p.days)}
                    className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                      days === p.days
                        ? "bg-accent/10 text-accent"
                        : "text-ink-muted hover:bg-surface-muted hover:text-ink"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th className="px-5 py-2.5">User</th>
                    <th className="px-3 py-2.5 text-right">Docs</th>
                    <th className="px-3 py-2.5 text-right">Completed</th>
                    <th className="px-3 py-2.5 text-right">Failed</th>
                    <th className="px-3 py-2.5 text-right">Fields</th>
                    <th className="px-3 py-2.5 text-right">Corrected</th>
                    <th className="px-3 py-2.5 text-right">Correction %</th>
                    <th className="px-3 py-2.5 text-right">Avg time</th>
                    <th className="px-5 py-2.5 text-right">Last activity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border/70 tabular-nums">
                  {data.users.map((u) => (
                    <tr key={u.user_id}>
                      <td className="px-5 py-2.5">
                        <p className="font-medium">{u.username}</p>
                        <p className="text-xs text-ink-muted">{u.email}</p>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <CountButton
                          value={u.docs_total}
                          onClick={() => setDrill({ user: u, kind: "docs" })}
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <CountButton
                          value={u.docs_completed}
                          onClick={() => setDrill({ user: u, kind: "completed" })}
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <CountButton
                          value={u.docs_failed}
                          tone="bad"
                          onClick={() => setDrill({ user: u, kind: "failed" })}
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <CountButton
                          value={u.fields_extracted}
                          onClick={() => setDrill({ user: u, kind: "fields" })}
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <CountButton
                          value={u.fields_corrected}
                          tone="bad"
                          onClick={() => setDrill({ user: u, kind: "corrected" })}
                        />
                      </td>
                      <td className="px-3 py-2.5 text-right">{u.correction_rate}%</td>
                      <td className="px-3 py-2.5 text-right">{fmtSeconds(u.avg_processing_seconds)}</td>
                      <td className="px-5 py-2.5 text-right text-xs text-ink-muted">
                        {fmtDate(u.last_activity)}
                      </td>
                    </tr>
                  ))}
                  {!data.users.length && (
                    <tr>
                      <td colSpan={9} className="px-5 py-8 text-center text-ink-muted">
                        No activity in this period.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Uploads chart */}
            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <h3 className="text-sm font-semibold">Uploads per day</h3>
              {data.activity_timeline.length ? (
                <div className="mt-3 h-56">
                  <Bar data={uploadsChart} options={chartOptions} />
                </div>
              ) : (
                <p className="mt-4 text-sm text-ink-muted">No uploads in this period.</p>
              )}
            </div>

            {/* Accuracy trend chart */}
            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <h3 className="text-sm font-semibold">Correction rate trend</h3>
              {data.accuracy_trend.length ? (
                <div className="mt-3 h-56">
                  <Line data={trendChart} options={chartOptions} />
                </div>
              ) : (
                <p className="mt-4 text-sm text-ink-muted">No feedback in this period.</p>
              )}
              <p className="mt-2 text-xs text-ink-muted">
                Percentage of feedback marking a field wrong, per day — lower is better.
              </p>
            </div>

            {/* Problem fields */}
            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <h3 className="text-sm font-semibold">Most-corrected fields</h3>
              {data.field_problem_ranking.length ? (
                <ul className="mt-3 space-y-2">
                  {data.field_problem_ranking.map((f) => {
                    const max = data.field_problem_ranking[0]?.corrections || 1;
                    return (
                      <li key={f.field_key} className="flex items-center gap-3 text-sm">
                        <span className="w-56 shrink-0 truncate font-mono text-xs">{f.field_key}</span>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                          <div
                            className="h-full rounded-full bg-amber-500/80"
                            style={{ width: `${(f.corrections / max) * 100}%` }}
                          />
                        </div>
                        <span className="w-8 text-right tabular-nums">{f.corrections}</span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-ink-muted">No corrections in this period.</p>
              )}
            </div>

            {/* Failure reasons */}
            <div className="rounded-lg border border-surface-border bg-surface p-5">
              <h3 className="text-sm font-semibold">Top failure reasons</h3>
              {data.failure_stats.top_error_codes.length ? (
                <ul className="mt-3 space-y-2">
                  {data.failure_stats.top_error_codes.map((e) => (
                    <li key={e.error_code} className="flex items-center justify-between text-sm">
                      <span className="font-mono text-xs">{e.error_code}</span>
                      <span className="tabular-nums">{e.count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-ink-muted">No failures in this period.</p>
              )}
            </div>
          </div>
        </>
      ) : null}

      {drill && (
        <DrillDownModal
          user={drill.user}
          kind={drill.kind}
          days={days}
          onClose={() => setDrill(null)}
        />
      )}
    </div>
  );
}
