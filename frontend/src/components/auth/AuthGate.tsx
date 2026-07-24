"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Spokes } from "@/components/ui/Spokes";
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
      <div
        className="bg-surface-muted text-ink-muted dark:text-accent"
        // Inline layout: this renders before CSS may be ready during bootstrap.
        style={{
          display: "flex",
          minHeight: "100vh",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spokes className="h-7 w-7" size={28} />
      </div>
    );
  }

  if (!user && !isPublic) {
    return null;
  }

  return <>{children}</>;
}
