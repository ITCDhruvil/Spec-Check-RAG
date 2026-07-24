"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { CheckIcon } from "@/components/ui/icons";
import { SpokesLoader } from "@/components/ui/Spokes";
import {
  getFeatureSettings,
  updateFeatureSettings,
} from "@/lib/api/settings";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { useAuth } from "@/providers/auth-provider";

const ROLES = [
  { key: "admin", label: "Admin" },
  { key: "manager", label: "Manager" },
  { key: "team_leader", label: "Team Leader" },
  { key: "user", label: "General User" },
];

const FEATURE_META: Record<string, { label: string; description: string }> = {
  ai_insights: {
    label: "AI analysis",
    description: "LLM-generated insights on the Insights page (root causes, recommendations).",
  },
  insights_dashboard: {
    label: "Insights dashboard",
    description: "Team activity, accuracy trends, and per-user statistics.",
  },
  export: {
    label: "Export to Excel",
    description: "Export page with Summary / Per-User / Documents sheets.",
  },
  admin_notes: {
    label: "Admin notes",
    description: "Editable per-document notes summarizing results and corrections.",
  },
};

export default function SettingsPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const [local, setLocal] = useState<Record<string, string[]>>({});
  const [saved, setSaved] = useState(false);

  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "Settings",
    subtitle: "Permissions, features, and defaults",
  });

  useEffect(() => {
    if (!loading && user && !user.is_admin) {
      router.replace("/");
    }
  }, [user, loading, router]);

  const query = useQuery({
    queryKey: ["feature-settings"],
    queryFn: getFeatureSettings,
    enabled: Boolean(user?.is_admin),
  });

  const saveMutation = useMutation({
    mutationFn: (updates: Record<string, string[]>) => updateFeatureSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feature-settings"] });
      setLocal({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  if (loading || !user?.is_admin) {
    return loading ? (
      <SpokesLoader className="py-24" />
    ) : (
      <div className="py-12 text-center text-ink-muted">Redirecting…</div>
    );
  }

  const data = query.data;
  const current: Record<string, string[]> = {
    ...(data?.features ?? {}),
    ...local,
  };

  function toggle(feature: string, role: string) {
    const roles = new Set(current[feature] ?? []);
    if (role === "admin") return; // admin always has every feature
    if (roles.has(role)) roles.delete(role);
    else roles.add(role);
    setLocal((l) => ({ ...l, [feature]: Array.from(roles) }));
  }

  function resetToDefault(feature: string) {
    if (!data) return;
    setLocal((l) => ({ ...l, [feature]: data.defaults[feature] ?? [] }));
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {query.isPending ? (
        <SpokesLoader className="py-16" />
      ) : query.isError ? (
        <p className="py-8 text-center text-sm text-red-600">
          {(query.error as Error).message}
        </p>
      ) : (
        <>
          {/* Permissions: feature × role matrix */}
          <div className="rounded-lg border border-surface-border bg-surface">
            <div className="border-b border-surface-border px-5 py-3">
              <h3 className="text-sm font-semibold">Permissions</h3>
              <p className="mt-0.5 text-xs text-ink-muted">
                Choose which roles can use each feature. Admin always has every
                feature. "Default" restores the recommended setting.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th className="px-5 py-2.5">Feature</th>
                    {ROLES.map((r) => (
                      <th key={r.key} className="px-3 py-2.5 text-center">
                        {r.label}
                      </th>
                    ))}
                    <th className="px-5 py-2.5 text-right">Default</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border/70">
                  {Object.entries(FEATURE_META).map(([feature, meta]) => (
                    <tr key={feature}>
                      <td className="px-5 py-3">
                        <p className="font-medium">{meta.label}</p>
                        <p className="text-xs text-ink-muted">{meta.description}</p>
                      </td>
                      {ROLES.map((r) => {
                        const on = (current[feature] ?? []).includes(r.key) || r.key === "admin";
                        return (
                          <td key={r.key} className="px-3 py-3 text-center">
                            <button
                              type="button"
                              onClick={() => toggle(feature, r.key)}
                              disabled={r.key === "admin"}
                              aria-pressed={on}
                              title={r.key === "admin" ? "Admin always enabled" : `Toggle for ${r.label}`}
                              className={`relative inline-flex h-5 w-9 rounded-full border-2 border-transparent transition-colors ${
                                on ? "bg-accent" : "bg-surface-muted"
                              } ${r.key === "admin" ? "opacity-50" : ""}`}
                            >
                              <span
                                className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                                  on ? "translate-x-4" : "translate-x-0"
                                }`}
                              />
                            </button>
                          </td>
                        );
                      })}
                      <td className="px-5 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => resetToDefault(feature)}
                          className="text-xs text-ink-muted hover:text-ink hover:underline"
                        >
                          Default
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-3 border-t border-surface-border px-5 py-3">
              <button
                type="button"
                onClick={() => saveMutation.mutate(local)}
                disabled={Object.keys(local).length === 0 || saveMutation.isPending}
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
              >
                {saveMutation.isPending ? "Saving…" : "Save permissions"}
              </button>
              {saved && (
                <span className="inline-flex items-center gap-1 text-sm text-emerald-600">
                  <CheckIcon className="h-4 w-4" /> Saved
                </span>
              )}
              {saveMutation.isError && (
                <span className="text-sm text-red-600">
                  {(saveMutation.error as Error).message}
                </span>
              )}
            </div>
          </div>

          {/* Shortcuts to related settings */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Link
              href="/users"
              className="rounded-lg border border-surface-border bg-surface p-5 transition-colors hover:border-accent/40"
            >
              <p className="text-sm font-semibold">Users</p>
              <p className="mt-1 text-xs text-ink-muted">
                Create accounts, assign roles, manage passwords and access.
              </p>
            </Link>
            <Link
              href="/export"
              className="rounded-lg border border-surface-border bg-surface p-5 transition-colors hover:border-accent/40"
            >
              <p className="text-sm font-semibold">Export</p>
              <p className="mt-1 text-xs text-ink-muted">
                Preview and download analytics reports; per-user or overall scope.
              </p>
            </Link>
            <Link
              href="/feedback-insights"
              className="rounded-lg border border-surface-border bg-surface p-5 transition-colors hover:border-accent/40"
            >
              <p className="text-sm font-semibold">AI &amp; fine-tuning</p>
              <p className="mt-1 text-xs text-ink-muted">
                Feedback data, fine-tune jobs, thresholds, and model settings.
              </p>
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
