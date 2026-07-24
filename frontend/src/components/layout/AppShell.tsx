"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { ChangePasswordModal } from "@/components/auth/ChangePasswordModal";
import {
  DownloadIcon,
  GearIcon,
  KeyIcon,
  MoonIcon,
  SignOutIcon,
  UserCircleIcon,
} from "@/components/ui/icons";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import {
  PageHeaderProvider,
  usePageHeaderData,
} from "@/lib/pageHeaderContext";
import { truncateFilename } from "@/lib/truncate";
import { useAuth } from "@/providers/auth-provider";

const baseNav = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
];

// Management (admin / manager / team leader) pages.
const managementNav = [
  { href: "/user-insights", label: "Insights" },
  { href: "/feedback-insights", label: "Feedback" },
];

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  manager: "Manager",
  team_leader: "Team Leader",
  user: "General User",
};

type ThemeMode = "light" | "dark";
const THEME_STORAGE_KEY = "spec-check-theme";

function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme;
}

function isSplitPanelRoute(pathname: string) {
  return /^\/documents\/[^/]+\/(summary|chat|manual)\/?$/.test(pathname);
}

/** Extract the document id from a /documents/<id>/... path, or null. */
function documentIdFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/documents\/([^/]+)\//);
  return m ? m[1] : null;
}

function isFullWidthRoute(pathname: string) {
  return (
    pathname === "/" ||
    pathname === "/upload" ||
    pathname === "/feedback-insights" ||
    pathname === "/user-insights" ||
    pathname === "/users" ||
    pathname === "/export" ||
    pathname === "/settings"
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <PageHeaderProvider>
      <AppShellInner>{children}</AppShellInner>
    </PageHeaderProvider>
  );
}

function ProfileMenu({
  onChangePassword,
  theme,
  onToggleTheme,
}: {
  onChangePassword: () => void;
  theme: ThemeMode;
  onToggleTheme: () => void;
}) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Close on click outside / Escape.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  const displayName =
    [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
  const initials = (displayName || user.email)
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        title="Profile"
        className="flex h-9 w-9 items-center justify-center rounded-full border border-surface-border bg-surface-muted text-sm font-semibold text-ink transition hover:border-accent/40 hover:bg-accent/5"
      >
        {initials || <UserCircleIcon className="h-5 w-5" />}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 z-40 w-72 rounded-lg border border-surface-border bg-surface shadow-lg"
        >
          <div className="flex items-center justify-between gap-3 border-b border-surface-border px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{displayName}</p>
              <p className="truncate text-xs text-ink-muted">{user.email}</p>
            </div>
            <span className="shrink-0 rounded-full border border-accent/25 bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </div>
          <div className="p-1.5">
            {user.is_admin && (
              <Link
                href="/settings"
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink hover:bg-surface-muted"
              >
                <GearIcon className="h-4 w-4 text-ink-muted" />
                Settings
              </Link>
            )}
            <div className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-ink">
              <span className="flex items-center gap-2.5">
                <MoonIcon className="h-4 w-4 text-ink-muted" />
                Dark mode
              </span>
              <ThemeToggle isDark={theme === "dark"} onToggle={onToggleTheme} />
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onChangePassword();
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink hover:bg-surface-muted"
            >
              <KeyIcon className="h-4 w-4 text-ink-muted" />
              Change password
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                logout();
                router.replace("/login");
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
            >
              <SignOutIcon className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>("light");
  const pageHeader = usePageHeaderData();

  // useLayoutEffect (not useEffect) so the toggle's knob position is correct
  // before the browser paints — the theme itself is already applied
  // pre-hydration by the inline script in layout.tsx.
  useLayoutEffect(() => {
    const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    const nextTheme: ThemeMode = savedTheme === "dark" ? "dark" : "light";
    setTheme(nextTheme);
    applyTheme(nextTheme);
  }, []);

  function toggleTheme() {
    setTheme((current) => {
      const nextTheme: ThemeMode = current === "dark" ? "light" : "dark";
      window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
      applyTheme(nextTheme);
      return nextTheme;
    });
  }

  if (pathname === "/login") {
    return <>{children}</>;
  }

  // "Manual" appears when a document is open (per-document keyword search).
  const openDocId = documentIdFromPath(pathname);
  const nav = [
    ...baseNav,
    ...(openDocId ? [{ href: `/documents/${openDocId}/manual`, label: "Manual" }] : []),
    ...(user?.is_management ? managementNav : []),
    ...(user?.is_admin ? [{ href: "/users", label: "Users" }] : []),
  ];

  const splitPanel = isSplitPanelRoute(pathname);
  const fullWidth = isFullWidthRoute(pathname);

  const headerInnerClass = fullWidth || splitPanel
    ? "flex w-full items-center justify-between px-6 py-4"
    : "mx-auto flex max-w-6xl items-center justify-between px-6 py-4";

  return (
    <div
      className={`flex min-h-screen flex-col bg-surface-muted text-ink ${
        splitPanel ? "h-screen overflow-hidden" : ""
      }`}
    >
      <header className="sticky top-0 z-30 shrink-0 border-b border-surface-border bg-surface">
        <div className={headerInnerClass}>
          {pageHeader ? (
            <div className="flex min-w-0 items-center gap-4">
              {/* Back link only for non-dashboard targets — the nav already has Dashboard. */}
              {pageHeader.backHref !== "/" && (
                <>
                  <Link
                    href={pageHeader.backHref}
                    className="shrink-0 text-sm text-ink-muted transition hover:text-ink"
                  >
                    ← {pageHeader.backLabel}
                  </Link>
                  <span className="h-5 w-px shrink-0 bg-surface-border" aria-hidden />
                </>
              )}
              <div className="flex min-w-0 items-baseline gap-3">
                <h1 className="shrink-0 text-lg font-semibold">
                  {pageHeader.title}
                </h1>
                {pageHeader.subtitle && (
                  <p
                    className="truncate text-sm text-ink-muted"
                    title={pageHeader.subtitle}
                  >
                    {truncateFilename(pageHeader.subtitle, 56)}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                Spec Check
              </p>
              <h1 className="text-lg font-semibold">Tender Specification Review</h1>
            </div>
          )}
          <div className="flex shrink-0 items-center gap-6">
            <nav className="flex gap-1 text-sm">
              {nav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded px-2.5 py-1.5 transition-colors hover:bg-surface-muted hover:text-ink ${
                    pathname === item.href
                      ? "font-medium text-ink"
                      : "text-ink-muted"
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            {user && (
              <Link
                href="/export"
                title="Export analytics to Excel"
                className={`flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm transition-colors hover:bg-surface-muted hover:text-ink ${
                  pathname === "/export" ? "font-medium text-ink" : "text-ink-muted"
                }`}
              >
                <DownloadIcon className="h-4 w-4" />
                Export
              </Link>
            )}
            {user && (
              <div className="border-l border-surface-border pl-5">
                <ProfileMenu
                  onChangePassword={() => setPasswordModalOpen(true)}
                  theme={theme}
                  onToggleTheme={toggleTheme}
                />
              </div>
            )}
          </div>
        </div>
      </header>
      <ChangePasswordModal
        open={passwordModalOpen}
        onClose={() => setPasswordModalOpen(false)}
      />
      <main
        className={
          splitPanel
            ? "flex min-h-0 flex-1 flex-col overflow-hidden"
            : fullWidth
              ? "w-full px-6 py-8"
              : "mx-auto max-w-6xl px-6 py-8"
        }
      >
        {children}
      </main>
    </div>
  );
}
