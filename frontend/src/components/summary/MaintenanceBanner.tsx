"use client";

import { useEffect, useState } from "react";
import { getHealthStatus } from "@/lib/api/intelligence";

/**
 * Polls /api/health/ every 15 seconds and shows a banner when
 * the backend is in maintenance mode (fine-tuning in progress).
 * Hides automatically once maintenance ends.
 */
export function MaintenanceBanner() {
  const [maintenance, setMaintenance] = useState(false);
  const [reason, setReason] = useState("");
  const [expectedEnd, setExpectedEnd] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const h = await getHealthStatus();
        if (!cancelled) {
          setMaintenance(h.maintenance ?? false);
          setReason(h.reason ?? "");
          setExpectedEnd(h.expected_end ?? "");
        }
      } catch {
        // silent — don't show error if health endpoint unreachable
      }
    }

    check();
    const interval = setInterval(check, 15_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!maintenance) return null;

  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm dark:border-amber-500/30 dark:bg-amber-500/10">
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden
      >
        <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 4a.75.75 0 01.75.75v3a.75.75 0 01-1.5 0v-3A.75.75 0 018 5zm0 6.5a.875.875 0 110-1.75.875.875 0 010 1.75z" />
      </svg>
      <div>
        <p className="font-semibold text-amber-800 dark:text-amber-300">Model update in progress</p>
        <p className="mt-0.5 text-amber-700 dark:text-amber-200">
          {reason || "A fine-tuning job is running to improve extraction accuracy from your feedback."}
          {" "}New analyses will start automatically when it completes.
          {expectedEnd && (
            <span className="ml-1 text-amber-800 dark:text-amber-300">Expected: {expectedEnd}</span>
          )}
        </p>
      </div>
    </div>
  );
}
