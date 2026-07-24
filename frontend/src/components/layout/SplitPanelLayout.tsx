"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { usePdfNavigation } from "@/lib/pdfNavigationContext";

const PREVIEW_COLLAPSED_KEY = "document-preview-collapsed";

interface SplitPanelLayoutProps {
  header?: ReactNode;
  left: ReactNode;
  right: ReactNode;
  rightTitle?: string;
  rightCollapsible?: boolean;
}

function readCollapsedPreference(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(PREVIEW_COLLAPSED_KEY) === "1";
}

export function SplitPanelLayout({
  header,
  left,
  right,
  rightTitle = "Document preview",
  rightCollapsible = true,
}: SplitPanelLayoutProps) {
  const [previewCollapsed, setPreviewCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const {
    setCanJump,
    registerExpandPreview,
    unregisterExpandPreview,
    registerCollapsePreview,
    unregisterCollapsePreview,
  } = usePdfNavigation();

  useEffect(() => {
    setPreviewCollapsed(readCollapsedPreference());
    setHydrated(true);
  }, []);

  const setCollapsed = useCallback((collapsed: boolean) => {
    setPreviewCollapsed(collapsed);
    sessionStorage.setItem(PREVIEW_COLLAPSED_KEY, collapsed ? "1" : "0");
  }, []);

  // The preview panel is reachable whenever this layout is mounted (it can be
  // collapsed but not removed). Jump is therefore always available — clicking
  // it expands a collapsed panel. This decouples canJump from the preview's
  // mount state, which unmounts when collapsed.
  useEffect(() => {
    if (!rightCollapsible) return;
    setCanJump(true);
    registerExpandPreview(() => setCollapsed(false));
    registerCollapsePreview(() => setCollapsed(true));
    return () => {
      setCanJump(false);
      unregisterExpandPreview();
      unregisterCollapsePreview();
    };
  }, [
    rightCollapsible,
    setCanJump,
    registerExpandPreview,
    unregisterExpandPreview,
    registerCollapsePreview,
    unregisterCollapsePreview,
    setCollapsed,
  ]);

  const showPreview = !rightCollapsible || !previewCollapsed;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {header && (
        <div className="shrink-0 border-b border-surface-border bg-surface px-6 py-4">
          {header}
        </div>
      )}

      <div className="relative flex min-h-0 flex-1 flex-col">
        <div
          className={`grid min-h-0 flex-1 grid-cols-1 ${
            showPreview ? "lg:grid-cols-2" : "lg:grid-cols-1"
          }`}
        >
          <div className="min-h-0 overflow-y-auto border-b border-surface-border px-6 py-4 lg:border-b-0 lg:border-r">
            {left}
          </div>

          {showPreview && (
            <div className="flex min-h-0 flex-col overflow-hidden px-6 py-4">
              <div
                id="document-preview-panel"
                className="min-h-0 flex-1 overflow-hidden"
              >
                {right}
              </div>
            </div>
          )}
        </div>

        {rightCollapsible && hydrated && previewCollapsed && (
          <>
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              className="absolute right-0 top-1/2 z-20 hidden -translate-y-1/2 rounded-l-md border border-r-0 border-surface-border bg-surface px-1.5 py-3 shadow-sm transition-colors hover:border-accent/40 hover:bg-accent/5 lg:inline-flex lg:flex-col lg:items-center lg:gap-1"
              aria-expanded={false}
              aria-controls="document-preview-panel"
              title={`Show ${rightTitle}`}
            >
              <svg
                className="h-4 w-4 text-ink-muted"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                aria-hidden
              >
                <path
                  d="M6 4l-4 4 4 4M2 8h12"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span
                className="text-[10px] font-medium uppercase tracking-wide text-ink-muted"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                Preview
              </span>
            </button>

            <button
              type="button"
              onClick={() => setCollapsed(false)}
              className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-md transition-colors hover:border-accent/40 hover:bg-accent/5 hover:text-accent lg:hidden"
              aria-expanded={false}
              aria-controls="document-preview-panel"
            >
              <svg
                className="h-4 w-4"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                aria-hidden
              >
                <path
                  d="M6 4l-4 4 4 4M2 8h12"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {rightTitle}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
