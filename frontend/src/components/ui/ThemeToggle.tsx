"use client";

import { MoonIcon, SunIcon } from "@/components/ui/icons";

/**
 * Compact sliding sun/moon switch for the profile menu.
 *
 * By design the *active* icon inside the knob is reversed from the usual
 * convention: dark mode highlights the sun, light mode highlights the moon.
 */
export function ThemeToggle({
  isDark,
  onToggle,
}: {
  isDark: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="relative inline-flex h-7 w-[52px] shrink-0 items-center rounded-full border border-surface-border bg-surface-muted transition-colors"
    >
      <MoonIcon className="absolute left-[7px] top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
      <SunIcon className="absolute right-[7px] top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
      <span
        className={`absolute left-[3px] top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full bg-accent shadow-sm transition-transform duration-300 ease-out ${
          isDark ? "translate-x-[26px]" : "translate-x-0"
        }`}
      >
        {isDark ? (
          <SunIcon className="h-3 w-3 text-white" />
        ) : (
          <MoonIcon className="h-3 w-3 text-white" />
        )}
      </span>
    </button>
  );
}
