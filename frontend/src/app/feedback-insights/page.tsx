"use client";

import { Fragment, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  XMarkIcon,
} from "@/components/ui/icons";
import { SpokesLoader } from "@/components/ui/Spokes";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { useAuth } from "@/providers/auth-provider";
import {
  getFeedbackStats,
  getFeedbackList,
  deleteFeedback,
  getFineTuneJobs,
  triggerFineTune,
  getAppSettings,
  updateAppSettings,
  type FeedbackRow,
  type FineTuneJobRow,
  type AppSettings,
} from "@/lib/api/intelligence";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EXTRACTION_TYPE_LABELS: Record<string, string> = {
  eligibility_criteria: "Eligibility / Project ID",
  submission_deadlines: "Submission Deadlines",
  technical_requirements: "Technical Requirements",
  scope_of_work: "Scope of Work",
  payment_terms: "Payment Terms",
  penalties_and_risks: "Bonds & Penalties",
  mandatory_documents: "Mandatory Documents",
  evaluation_criteria: "Evaluation Criteria",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-surface-muted text-ink-muted border-surface-border",
  uploading: "bg-accent/10 text-accent border-accent/30",
  running: "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30",
  succeeded: "bg-green-100 text-green-800 border-green-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30",
  failed: "bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/30",
  cancelled: "bg-surface-muted text-ink-muted border-surface-border",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? STATUS_COLORS.pending;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}

function TabBar({ tabs, active, onChange }: {
  tabs: string[];
  active: string;
  onChange: (t: string) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-surface-border">
      {tabs.map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onChange(t)}
          className={`px-4 py-2.5 text-sm font-medium transition-colors ${
            active === t
              ? "border-b-2 border-accent text-accent"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Overview
// ---------------------------------------------------------------------------

function OverviewTab() {
  const { data, isPending } = useQuery({
    queryKey: ["feedback-stats"],
    queryFn: getFeedbackStats,
    refetchInterval: 30_000,
  });

  if (isPending) return <Spinner />;
  if (!data) return null;

  const threshold = data.settings.threshold;

  return (
    <div className="space-y-6">
      {/* Top stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Total feedback" value={data.total} />
        <StatCard label="Thumbs up" value={data.up} />
        <StatCard label="Thumbs down" value={data.down} />
        <StatCard label="With correction" value={data.with_correction} sub="ready for fine-tuning" />
      </div>

      {/* Per-type progress toward threshold */}
      <div className="rounded-lg border border-surface-border bg-surface">
        <div className="border-b border-surface-border px-4 py-3">
          <p className="text-sm font-semibold">Progress toward fine-tune threshold ({threshold} corrections/type)</p>
        </div>
        <div className="divide-y divide-surface-border/60">
          {data.by_type.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-ink-muted">No feedback collected yet.</p>
          )}
          {data.by_type.map((row) => {
            const pct = Math.min(100, Math.round((row.with_correction / threshold) * 100));
            const hasFtModel = Boolean(data.fine_tuned_models[row.extraction_type]);
            return (
              <div key={row.extraction_type} className="px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">
                      {EXTRACTION_TYPE_LABELS[row.extraction_type] ?? row.extraction_type}
                    </p>
                    <p className="flex items-center gap-1 text-xs text-ink-muted">
                      {row.with_correction}/{threshold} corrections
                      <span className="mx-0.5">·</span>
                      {row.up} <ThumbsUpIcon className="h-3 w-3 text-emerald-600" />
                      <span className="mx-0.5">·</span>
                      {row.down} <ThumbsDownIcon className="h-3 w-3 text-red-500" />
                      {hasFtModel && <span className="ml-2 font-medium text-emerald-600">Fine-tuned</span>}
                    </p>
                  </div>
                  <div className="w-32 shrink-0">
                    <div className="h-2 rounded-full bg-surface-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-emerald-500" : "bg-accent"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="mt-0.5 text-right text-[10px] tabular-nums text-ink-muted">{pct}%</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Learning loop: did corrections actually stop the mistakes? */}
      {data.learning && data.learning.totals.corrections > 0 && (
        <div className="rounded-lg border border-surface-border bg-surface">
          <div className="border-b border-surface-border px-4 py-3">
            <p className="text-sm font-semibold">Learning effectiveness</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              Each correction is re-checked when its document is re-analyzed:
              resolved = the mistake stopped, recurring = it happened again
              (highest priority for prompt tuning / fine-tuning).
            </p>
          </div>
          <div className="grid grid-cols-3 divide-x divide-surface-border border-b border-surface-border text-center">
            <div className="px-4 py-3">
              <p className="text-lg font-semibold tabular-nums text-emerald-600">
                {data.learning.totals.resolved}
              </p>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted">Resolved</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-lg font-semibold tabular-nums text-red-600">
                {data.learning.totals.recurred}
              </p>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted">Recurring</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-lg font-semibold tabular-nums text-ink-muted">
                {data.learning.totals.pending}
              </p>
              <p className="text-[11px] uppercase tracking-wide text-ink-muted">Awaiting re-check</p>
            </div>
          </div>
          <div className="divide-y divide-surface-border/60">
            {data.learning.per_field.map((f) => (
              <div key={f.field_key} className="flex items-center justify-between px-4 py-2 text-xs">
                <span className="font-mono">{f.field_key}</span>
                <span className="flex items-center gap-3 tabular-nums">
                  <span className="text-emerald-600">{f.resolved} resolved</span>
                  <span className={f.recurred ? "font-medium text-red-600" : "text-ink-muted"}>
                    {f.recurred} recurring
                  </span>
                  <span className="text-ink-muted">{f.pending} pending</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active fine-tuned models */}
      {Object.keys(data.fine_tuned_models).length > 0 && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-500/30 dark:bg-emerald-500/10">
          <p className="mb-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">Active fine-tuned models</p>
          <div className="space-y-1">
            {Object.entries(data.fine_tuned_models).map(([etype, modelId]) => (
              <p key={etype} className="text-xs text-emerald-700 dark:text-emerald-200">
                <span className="font-medium">{EXTRACTION_TYPE_LABELS[etype] ?? etype}:</span>{" "}
                <code className="rounded bg-emerald-100 px-1 py-0.5 dark:bg-emerald-500/15">{modelId}</code>
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Active jobs */}
      {data.active_jobs.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10">
          <p className="mb-2 text-sm font-semibold text-amber-800 dark:text-amber-300">Active fine-tune jobs</p>
          {data.active_jobs.map((j) => (
            <p key={j.id} className="text-xs text-amber-700 dark:text-amber-200">
              {EXTRACTION_TYPE_LABELS[j.extraction_type] ?? j.extraction_type} —{" "}
              <StatusBadge status={j.status} /> · {j.feedback_count} examples · est. ${j.estimated_cost_usd.toFixed(3)}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Feedback Data
// ---------------------------------------------------------------------------

function FeedbackDataTab() {
  const qc = useQueryClient();
  const [filterType, setFilterType] = useState("");
  const [filterRating, setFilterRating] = useState("");
  const [page, setPage] = useState(1);

  const { data, isPending } = useQuery({
    queryKey: ["feedback-list", filterType, filterRating, page],
    queryFn: () =>
      getFeedbackList({
        extraction_type: filterType || undefined,
        rating: filterRating || undefined,
        page,
        page_size: 50,
      }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteFeedback(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feedback-list"] });
      qc.invalidateQueries({ queryKey: ["feedback-stats"] });
    },
  });

  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
          className="rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-ink"
        >
          <option value="">All types</option>
          {Object.entries(EXTRACTION_TYPE_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <select
          value={filterRating}
          onChange={(e) => { setFilterRating(e.target.value); setPage(1); }}
          className="rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-ink"
        >
          <option value="">All ratings</option>
          <option value="up">Correct</option>
          <option value="down">Incorrect</option>
        </select>
        {data && (
          <p className="ml-auto self-center text-xs text-ink-muted">{data.count} entries</p>
        )}
      </div>

      {isPending && <Spinner />}

      {data && (
        <>
          <div className="rounded-lg border border-surface-border overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-surface-muted/60">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Field</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Type</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Rating</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Extracted</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Correct</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Used</th>
                  <th className="px-3 py-2 text-left font-medium text-ink-muted">Date</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/60">
                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-ink-muted">No feedback yet.</td>
                  </tr>
                )}
                {data.results.map((row) => (
                  <Fragment key={row.id}>
                    <tr
                      className="cursor-pointer hover:bg-surface-muted/40"
                      onClick={() => setExpanded(expanded === row.id ? null : row.id)}
                    >
                      <td className="px-3 py-2 font-medium text-ink">{row.field_key}</td>
                      <td className="px-3 py-2 text-ink-muted">{EXTRACTION_TYPE_LABELS[row.extraction_type] ?? row.extraction_type}</td>
                      <td className="px-3 py-2">
                        {row.rating === "up" ? (
                          <ThumbsUpIcon className="h-4 w-4 text-emerald-600" />
                        ) : (
                          <ThumbsDownIcon className="h-4 w-4 text-red-500" />
                        )}
                      </td>
                      <td className="max-w-[140px] truncate px-3 py-2 text-ink-muted">{row.extracted_value || "—"}</td>
                      <td className={`max-w-[140px] truncate px-3 py-2 ${row.correct_value ? "font-medium text-emerald-700 dark:text-emerald-300" : "text-ink-muted"}`}>
                        {row.correct_value || "—"}
                      </td>
                      <td className="px-3 py-2">
                        {row.used_in_finetune
                          ? <CheckIcon className="h-4 w-4 text-emerald-600" />
                          : <span className="text-ink-muted">–</span>}
                      </td>
                      <td className="px-3 py-2 text-ink-muted whitespace-nowrap">
                        {new Date(row.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); deleteMut.mutate(row.id); }}
                          className="text-ink-muted/50 hover:text-red-500 transition-colors"
                          title="Delete"
                        ><XMarkIcon className="h-3.5 w-3.5" /></button>
                      </td>
                    </tr>
                    {expanded === row.id && (
                      <tr className="bg-surface-muted/30">
                        <td colSpan={8} className="px-4 py-3">
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs">
                            <div>
                              <p className="font-semibold text-ink-muted mb-1">Document</p>
                              <p className="text-ink truncate">{row.document_filename || row.document_id}</p>
                            </div>
                            <div>
                              <p className="font-semibold text-ink-muted mb-1">Issue type</p>
                              <p className="text-ink">{row.issue_type || "—"}</p>
                            </div>
                            {row.comment && (
                              <div className="sm:col-span-2">
                                <p className="font-semibold text-ink-muted mb-1">Comment</p>
                                <p className="text-ink">{row.comment}</p>
                              </div>
                            )}
                            {row.source_text_context && (
                              <div className="sm:col-span-2">
                                <p className="font-semibold text-ink-muted mb-1">Source context</p>
                                <p className="text-ink italic text-ink-muted">{row.source_text_context}</p>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded border border-surface-border px-3 py-1 hover:bg-surface-muted disabled:opacity-40"
            >
              <span className="inline-flex items-center gap-1"><ChevronLeftIcon className="h-3 w-3" /> Prev</span>
            </button>
            <span>Page {page} · {data.count} total</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * 50 >= data.count}
              className="rounded border border-surface-border px-3 py-1 hover:bg-surface-muted disabled:opacity-40"
            >
              <span className="inline-flex items-center gap-1">Next <ChevronRightIcon className="h-3 w-3" /></span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Fine-tune Jobs
// ---------------------------------------------------------------------------

function FineTuneJobsTab() {
  const qc = useQueryClient();
  const { data: statsData } = useQuery({ queryKey: ["feedback-stats"], queryFn: getFeedbackStats });
  const { data, isPending, refetch } = useQuery({
    queryKey: ["finetune-jobs"],
    queryFn: getFineTuneJobs,
    refetchInterval: 15_000,
  });

  const triggerMut = useMutation({
    mutationFn: (etype: string) => triggerFineTune(etype),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finetune-jobs"] });
      qc.invalidateQueries({ queryKey: ["feedback-stats"] });
    },
  });

  const [triggerType, setTriggerType] = useState("");

  // Types that have enough corrections to trigger
  const readyTypes = (statsData?.by_type ?? []).filter(
    (t) => t.with_correction >= (statsData?.settings.threshold ?? 50)
  );

  return (
    <div className="space-y-6">
      {/* Manual trigger */}
      <div className="rounded-lg border border-surface-border bg-surface px-4 py-4">
        <p className="mb-3 text-sm font-semibold">Manually trigger fine-tuning</p>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="mb-1 block text-xs text-ink-muted">Extraction type</label>
            <select
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value)}
              className="rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-ink"
            >
              <option value="">Select type…</option>
              {Object.entries(EXTRACTION_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            disabled={!triggerType || triggerMut.isPending}
            onClick={() => triggerType && triggerMut.mutate(triggerType)}
            className="rounded bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {triggerMut.isPending ? "Triggering…" : "Trigger fine-tune"}
          </button>
          {readyTypes.length > 0 && (
            <p className="text-xs text-emerald-700 self-end dark:text-emerald-300">
              Ready: {readyTypes.map((t) => EXTRACTION_TYPE_LABELS[t.extraction_type] ?? t.extraction_type).join(", ")}
            </p>
          )}
        </div>
        {triggerMut.isSuccess && (
          <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">
            Job started — ID {triggerMut.data.job_id.slice(0, 8)} · {triggerMut.data.feedback_count} examples · est. ${triggerMut.data.estimated_cost_usd.toFixed(3)}
          </p>
        )}
        {triggerMut.isError && (
          <p className="mt-2 text-xs text-red-600">
            {(triggerMut.error as Error).message}
          </p>
        )}
      </div>

      {/* Jobs list */}
      {isPending && <Spinner />}
      {data && (
        <div className="rounded-lg border border-surface-border overflow-hidden">
          <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
            <p className="text-sm font-semibold">All fine-tune jobs</p>
            <button
              type="button"
              onClick={() => refetch()}
              className="text-xs text-ink-muted hover:text-ink"
            >
              Refresh ↺
            </button>
          </div>
          {data.results.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-ink-muted">No jobs yet.</p>
          )}
          <div className="divide-y divide-surface-border/60">
            {data.results.map((job) => (
              <div key={job.id} className="px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-ink">
                      {EXTRACTION_TYPE_LABELS[job.extraction_type] ?? job.extraction_type}
                    </p>
                    <p className="text-xs text-ink-muted">
                      {job.feedback_count} examples · est. ${job.estimated_cost_usd.toFixed(3)} ·{" "}
                      {new Date(job.created_at).toLocaleString()}
                    </p>
                  </div>
                  <StatusBadge status={job.status} />
                </div>
                {job.azure_job_id && (
                  <p className="mt-1 text-[11px] text-ink-muted">
                    Azure job: <code className="rounded bg-surface-muted px-1">{job.azure_job_id}</code>
                    · Base: <code className="rounded bg-surface-muted px-1">{job.base_model}</code>
                  </p>
                )}
                {job.fine_tuned_model_id && (
                  <p className="mt-1 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
                    <CheckIcon className="mr-1 inline h-3.5 w-3.5" />
                    Active model: <code className="rounded bg-emerald-100 px-1 dark:bg-emerald-500/15">{job.fine_tuned_model_id}</code>
                  </p>
                )}
                {job.error_message && (
                  <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{job.error_message}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Settings
// ---------------------------------------------------------------------------

function SettingsTab() {
  const qc = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ["app-settings"], queryFn: getAppSettings });
  const [local, setLocal] = useState<Partial<AppSettings>>({});
  const [saved, setSaved] = useState(false);

  const updateMut = useMutation({
    mutationFn: (s: Partial<AppSettings>) => updateAppSettings(s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["app-settings"] });
      qc.invalidateQueries({ queryKey: ["feedback-stats"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  const current = { ...(data ?? {}), ...local } as AppSettings;

  function handleSave() {
    updateMut.mutate(local);
  }

  if (isPending) return <Spinner />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-lg border border-surface-border bg-surface divide-y divide-surface-border/60">

        {/* Fine-tuning toggle */}
        <div className="flex items-center justify-between px-4 py-4">
          <div>
            <p className="text-sm font-medium text-ink">Enable automatic fine-tuning</p>
            <p className="text-xs text-ink-muted mt-0.5">
              When ON, triggers a fine-tune job automatically when threshold is reached.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setLocal((l) => ({ ...l, FINETUNE_ENABLED: !current.FINETUNE_ENABLED }))}
            className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors ${
              current.FINETUNE_ENABLED ? "bg-accent" : "bg-surface-muted"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                current.FINETUNE_ENABLED ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Threshold */}
        <div className="px-4 py-4">
          <label className="block text-sm font-medium text-ink">
            Correction threshold per type
          </label>
          <p className="text-xs text-ink-muted mt-0.5 mb-2">
            Number of negative-feedback corrections needed before fine-tuning triggers.
          </p>
          <div className="flex items-center gap-3">
            <input
              type="number"
              min={10}
              max={500}
              step={10}
              value={current.FINETUNE_FEEDBACK_THRESHOLD ?? 50}
              onChange={(e) =>
                setLocal((l) => ({ ...l, FINETUNE_FEEDBACK_THRESHOLD: parseInt(e.target.value) }))
              }
              className="w-24 rounded border border-surface-border px-3 py-1.5 text-sm text-ink"
            />
            <span className="text-xs text-ink-muted">corrections</span>
          </div>
        </div>

        {/* Max cost */}
        <div className="px-4 py-4">
          <label className="block text-sm font-medium text-ink">
            Max cost per fine-tune run (USD)
          </label>
          <p className="text-xs text-ink-muted mt-0.5 mb-2">
            Job is aborted if estimated cost exceeds this. gpt-4o-mini ≈ $3/1M tokens.
          </p>
          <div className="flex items-center gap-3">
            <span className="text-sm text-ink-muted">$</span>
            <input
              type="number"
              min={0.5}
              max={50}
              step={0.5}
              value={current.FINETUNE_MAX_COST_USD ?? 5}
              onChange={(e) =>
                setLocal((l) => ({ ...l, FINETUNE_MAX_COST_USD: parseFloat(e.target.value) }))
              }
              className="w-24 rounded border border-surface-border px-3 py-1.5 text-sm text-ink"
            />
            <span className="text-xs text-ink-muted">USD</span>
          </div>
        </div>

        {/* Base model */}
        <div className="px-4 py-4">
          <label className="block text-sm font-medium text-ink">Base model for fine-tuning</label>
          <p className="text-xs text-ink-muted mt-0.5 mb-2">
            gpt-4o-mini is recommended — cheaper training, excellent on narrow tasks.
          </p>
          <select
            value={current.FINETUNE_BASE_MODEL ?? "gpt-4o-mini-2024-07-18"}
            onChange={(e) => setLocal((l) => ({ ...l, FINETUNE_BASE_MODEL: e.target.value }))}
            className="rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="gpt-4o-mini-2024-07-18">gpt-4o-mini-2024-07-18 (recommended)</option>
            <option value="gpt-4o-2024-08-06">gpt-4o-2024-08-06</option>
          </select>
        </div>
      </div>

      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={Object.keys(local).length === 0 || updateMut.isPending}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {updateMut.isPending ? "Saving…" : "Save settings"}
          </button>
          {saved && (
            <p className="inline-flex items-center gap-1 text-sm text-emerald-600">
              <CheckIcon className="h-4 w-4" /> Saved
            </p>
          )}
          {updateMut.isError && (
            <p className="text-sm text-red-600">{(updateMut.error as Error).message}</p>
          )}
          {Object.keys(local).length > 0 && !updateMut.isPending && (
            <button
              type="button"
              onClick={() => setLocal({})}
              className="text-xs text-ink-muted hover:text-ink"
            >
              Reset
            </button>
          )}
        </div>

        {/* Cost guide */}
        <div className="rounded-lg border border-surface-border bg-surface-muted/40 px-4 py-3 text-xs text-ink-muted">
          <p className="font-semibold text-ink mb-1">Fine-tuning cost reference</p>
          <p>gpt-4o-mini: <strong>$3.00</strong> / 1M training tokens (×epochs)</p>
          <p>gpt-4o: <strong>$25.00</strong> / 1M training tokens</p>
          <p className="mt-1">50 corrections × 3 epochs ≈ ~300k tokens ≈ <strong>$0.90</strong> on mini</p>
          <p>Inference on fine-tuned mini: <strong>$0.30/$1.20</strong> per 1M in/out</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

function Spinner() {
  return <SpokesLoader />;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const TABS = ["Overview", "Feedback Data", "Fine-tune Jobs", "Settings"];

export default function FeedbackInsightsPage() {
  const [tab, setTab] = useState("Overview");
  const { user, loading } = useAuth();
  const router = useRouter();

  // Page header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "Feedback Insights",
    subtitle: "Field feedback, fine-tuning progress, and settings",
  });

  useEffect(() => {
    if (!loading && user && !user.is_management) {
      router.replace("/");
    }
  }, [user, loading, router]);

  if (loading || !user?.is_management) {
    return loading ? (
      <SpokesLoader className="py-24" />
    ) : (
      <div className="py-12 text-center text-ink-muted">Redirecting…</div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="rounded-lg border border-surface-border bg-surface">
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
        <div className="p-5">
          {tab === "Overview" && <OverviewTab />}
          {tab === "Feedback Data" && <FeedbackDataTab />}
          {tab === "Fine-tune Jobs" && <FineTuneJobsTab />}
          {tab === "Settings" && <SettingsTab />}
        </div>
      </div>
    </div>
  );
}
