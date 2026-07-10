"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/providers/auth-provider";

const PUBLIC_ROUTES = new Set(["/login"]);

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_ROUTES.has(pathname);

  useEffect(() => {
    if (loading) return;

    if (!user && !isPublic) {
      router.replace("/login");
      return;
    }

    if (user && pathname === "/login") {
      router.replace("/");
    }
  }, [user, loading, pathname, isPublic, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-muted text-ink-muted">
        Loading…
      </div>
    );
  }

  if (!user && !isPublic) {
    return null;
  }

  return <>{children}</>;
}
