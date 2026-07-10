"use client";

import { useEffect, useState } from "react";

/**
 * False on the server and on the first client render so SSR HTML matches hydration.
 * Becomes true after mount — use to gate client-only UI (storage, query cache, etc.).
 */
export function useClientMounted(): boolean {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return mounted;
}
