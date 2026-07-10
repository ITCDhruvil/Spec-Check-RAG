"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { ChangePasswordModal } from "@/components/auth/ChangePasswordModal";
import { useAuth } from "@/providers/auth-provider";

const baseNav = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
];

const adminNav = [{ href: "/feedback-insights", label: "Feedback" }];

function isSplitPanelRoute(pathname: string) {
  return /^\/documents\/[^/]+\/(summary|chat)\/?$/.test(pathname);
}

function isFullWidthRoute(pathname: string) {
  return (
    pathname === "/" ||
    pathname === "/upload" ||
    pathname === "/feedback-insights" ||
    pathname === "/users"
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);

  if (pathname === "/login") {
    return <>{children}</>;
  }

  const nav = user?.is_admin
    ? [...baseNav, ...adminNav, { href: "/users", label: "Users" }]
    : baseNav;

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
      <header className="shrink-0 border-b border-surface-border bg-surface">
        <div className={headerInnerClass}>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Spec Check
            </p>
            <h1 className="text-lg font-semibold">Tender Specification Review</h1>
          </div>
          <div className="flex items-center gap-6">
            <nav className="flex gap-6 text-sm">
              {nav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-ink-muted transition hover:text-ink"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            {user && (
              <div className="flex items-center gap-3 border-l border-surface-border pl-6 text-sm">
                <span className="hidden text-ink-muted sm:inline">{user.email}</span>
                <button
                  type="button"
                  onClick={() => setPasswordModalOpen(true)}
                  className="rounded-md border border-surface-border px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted"
                >
                  Change password
                </button>
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                  className="rounded-md border border-surface-border px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted"
                >
                  Sign out
                </button>
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
