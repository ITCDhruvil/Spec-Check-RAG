"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { DownloadIcon } from "@/components/ui/icons";
import { Spokes, SpokesLoader } from "@/components/ui/Spokes";
import {
  downloadAnalyticsExport,
  fetchExportPreview,
  type ExportPreview,
} from "@/lib/api/insights";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { useAuth } from "@/providers/auth-provider";

const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 0, label: "All time" },
];

const TABS = ["Summary", "Per User", "Documents"] as const;
type Tab = (typeof TABS)[number];

function statusClass(status: string): string {
  if (status === "Correct") return "bg-green-100 text-green-800 dark:bg-emerald-500/10 dark:text-emerald-300";
  if (status === "Wrong") return "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-300";
  return "text-ink-muted italic";
}

function SummaryTab({ data }: { data: ExportPreview }) {
  return (
    <table className="w-full max-w-xl text-sm">
      <tbody className="divide-y divide-surface-border/70">
        {data.summary.map((row) => (
          <tr key={row.metric}>
            <td className="py-2 pr-6 font-medium">{row.metric}</td>
            <td className="py-2 text-ink-muted">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PerUserTab({ data }: { data: ExportPreview }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-muted">
            <th className="py-2 pr-4">User</th>
            <th className="px-3 py-2 text-right">Docs</th>
            <th className="px-3 py-2 text-right">Completed</th>
            <th className="px-3 py-2 text-right">Failed</th>
            <th className="px-3 py-2 text-right">Fields</th>
            <th className="px-3 py-2 text-right">Corrected</th>
            <th className="px-3 py-2 text-right">Correction %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border/70 tabular-nums">
          {data.per_user.map((u) => (
            <tr key={u.user_id}>
              <td className="py-2 pr-4">
                <p className="font-medium">{u.username}</p>
                <p className="text-xs text-ink-muted">{u.email}</p>
              </td>
              <td className="px-3 py-2 text-right">{u.docs_total}</td>
              <td className="px-3 py-2 text-right">{u.docs_completed}</td>
              <td className="px-3 py-2 text-right">{u.docs_failed}</td>
              <td className="px-3 py-2 text-right">{u.fields_extracted}</td>
              <td className="px-3 py-2 text-right">{u.fields_corrected}</td>
              <td className="px-3 py-2 text-right">{u.correction_rate}%</td>
            </tr>
          ))}
          {!data.per_user.length && (
            <tr>
              <td colSpan={7} className="py-8 text-center text-ink-muted">
                No activity in this period.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function DocumentsTab({ data }: { data: ExportPreview }) {
  const { columns, rows } = data.documents;
  if (!columns.length) {
    return <p className="py-8 text-center text-sm text-ink-muted">No documents in this period.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 border border-surface-border bg-surface px-3 py-2 text-left align-bottom">
              Field
            </th>
            {columns.map((doc) => (
              <th
                key={doc.id}
                colSpan={3}
                className="max-w-[320px] border border-surface-border bg-accent/5 px-3 py-2 text-left font-semibold"
                title={doc.filename}
              >
                <p className="truncate">{doc.filename}</p>
                <p className="text-[10px] font-normal text-ink-muted">
                  {doc.uploaded_by} · {doc.uploaded} · {doc.status}
                </p>
              </th>
            ))}
          </tr>
          <tr className="text-[10px] uppercase tracking-wide text-ink-muted">
            <th className="sticky left-0 z-10 border border-surface-border bg-surface px-3 py-1.5" />
            {columns.map((doc) => (
              <FragmentSub key={doc.id} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field_key}>
              <td className="sticky left-0 z-10 whitespace-nowrap border border-surface-border bg-surface px-3 py-1.5 font-medium">
                {row.label}
              </td>
              {row.cells.map((cell, i) => (
                <CellGroup key={i} cell={cell} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FragmentSub() {
  return (
    <>
      <th className="border border-surface-border bg-surface-muted/60 px-2 py-1.5 text-left">Status</th>
      <th className="border border-surface-border bg-surface-muted/60 px-2 py-1.5 text-left">Correction</th>
      <th className="border border-surface-border bg-surface-muted/60 px-2 py-1.5 text-left">Reason</th>
    </>
  );
}

function CellGroup({ cell }: { cell: { status: string; correction: string; reason: string } }) {
  return (
    <>
      <td className={`border border-surface-border px-2 py-1.5 ${statusClass(cell.status)}`}>
        {cell.status}
      </td>
      <td className="max-w-[180px] truncate border border-surface-border px-2 py-1.5" title={cell.correction}>
        {cell.correction || "—"}
      </td>
      <td className="max-w-[200px] truncate border border-surface-border px-2 py-1.5 text-ink-muted" title={cell.reason}>
        {cell.reason || "—"}
      </td>
    </>
  );
}

export default function ExportPage() {
  const { user, loading } = useAuth();
  const [days, setDays] = useState(30);
  const [scopeUser, setScopeUser] = useState<string>("");
  const [tab, setTab] = useState<Tab>("Summary");
  const [downloading, setDownloading] = useState(false);

  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "Export",
    subtitle: "Preview and download analytics as Excel",
  });

  const isManagement = Boolean(user?.is_management);

  const query = useQuery({
    queryKey: ["export-preview", days, scopeUser],
    queryFn: () => fetchExportPreview(days, scopeUser || undefined),
    enabled: Boolean(user),
  });

  const userOptions = useMemo(
    () => query.data?.per_user ?? [],
    [query.data]
  );

  async function handleDownload() {
    if (downloading) return;
    setDownloading(true);
    try {
      await downloadAnalyticsExport(days, scopeUser || undefined);
    } catch {
      window.alert("Export failed — please try again.");
    } finally {
      setDownloading(false);
    }
  }

  if (loading || !user) {
    return <SpokesLoader className="py-24" />;
  }

  const data = query.data;

  return (
    <div className="space-y-5">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
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
          {isManagement && (
            <select
              value={scopeUser}
              onChange={(e) => setScopeUser(e.target.value)}
              className="rounded border border-surface-border bg-surface px-2.5 py-1.5 text-xs"
            >
              <option value="">All users</option>
              {userOptions.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.username}
                </option>
              ))}
            </select>
          )}
        </div>
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading || query.isPending}
          className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
        >
          {downloading ? <Spokes className="h-4 w-4" size={16} /> : <DownloadIcon className="h-4 w-4" />}
          Download Excel
        </button>
      </div>

      {/* Tabs + content */}
      <div className="rounded-lg border border-surface-border bg-surface">
        <div className="flex gap-1 border-b border-surface-border px-3 pt-2">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded-t px-3.5 py-2 text-sm transition-colors ${
                tab === t
                  ? "border border-b-0 border-surface-border bg-surface font-medium text-ink"
                  : "text-ink-muted hover:bg-surface-muted hover:text-ink"
              }`}
              style={tab === t ? { marginBottom: -1 } : undefined}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="p-5">
          {query.isPending && <SpokesLoader />}
          {query.isError && (
            <p className="py-6 text-center text-sm text-red-600">
              {(query.error as Error).message}
            </p>
          )}
          {data && tab === "Summary" && <SummaryTab data={data} />}
          {data && tab === "Per User" && <PerUserTab data={data} />}
          {data && tab === "Documents" && <DocumentsTab data={data} />}
        </div>
      </div>
    </div>
  );
}
