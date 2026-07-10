"use client";

import { useState } from "react";

import {
  isJumpableCitation,
  normalizeCitationPage,
} from "@/lib/citationUtils";
import { usePdfNavigation } from "@/lib/pdfNavigationContext";
import type { SourceCitation } from "@/lib/types/intelligence";

function PageLabel({ page, isActive }: { page: number; isActive: boolean }) {
  return (
    <span
      className={`shrink-0 text-xs font-medium tabular-nums ${
        isActive ? "text-accent" : "text-ink-muted"
      }`}
    >
      page {page}
    </span>
  );
}

export function CitationPanel({ sources }: { sources: SourceCitation[] }) {
  const { activeHighlight } = usePdfNavigation();

  return (
    <div className="mt-3 w-full space-y-2">
      {sources.map((src, i) => {
        const jumpable = isJumpableCitation(src);
        const page = normalizeCitationPage(src.page);
        const activePage = normalizeCitationPage(activeHighlight?.page);
        const quote = src.source_text?.trim();
        const activeQuote = activeHighlight?.sourceText?.trim();
        const isActive =
          jumpable &&
          (quote && activeQuote
            ? activeQuote === quote ||
              activeQuote.startsWith(quote.slice(0, 48)) ||
              quote.startsWith(activeQuote.slice(0, 48))
            : page != null && activePage === page);
        return (
          <div
            key={i}
            className={`w-full rounded-xl border px-4 py-3 transition-colors ${
              isActive
                ? "border-accent/25 bg-accent/[0.03]"
                : "border-surface-border/80 bg-surface"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                {src.section ? (
                  <p className="text-sm font-semibold leading-snug text-ink">
                    {src.section}
                  </p>
                ) : (
                  <p className="text-sm font-semibold text-ink-muted">
                    Source {i + 1}
                  </p>
                )}
                {src.section_path && src.section_path !== src.section && (
                  <p className="mt-0.5 truncate text-xs text-ink-muted">
                    {src.section_path}
                  </p>
                )}
              </div>
              {page != null && (
                <PageLabel page={page} isActive={isActive} />
              )}
            </div>

            {src.source_text && (
              <blockquote className="mt-3 border-l-2 border-accent/20 pl-3 text-sm leading-relaxed text-ink-muted">
                {src.source_text.slice(0, 320)}
                {src.source_text.length > 320 ? "…" : ""}
              </blockquote>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function CitationToggle({
  open,
  count,
  onToggle,
}: {
  open: boolean;
  count: number;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="inline-flex items-center gap-1.5 rounded-full border border-surface-border bg-surface px-2.5 py-1 text-[11px] font-medium text-ink-muted transition-colors hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
    >
      <svg
        className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden
      >
        <path d="M2 4l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {open ? "Hide sources" : `${count} source${count !== 1 ? "s" : ""}`}
    </button>
  );
}

export function SourceCitationList({
  sources,
  signal,
  subtext,
}: {
  sources?: SourceCitation[];
  signal?: string;
  subtext?: string;
}) {
  const [open, setOpen] = useState(false);

  if (!sources?.length && !signal) return null;

  const hasCitations = Boolean(sources?.length);

  if (signal) {
    return (
      <div>
        <div className="flex items-start gap-4">
          <div className="w-[70%] min-w-0">
            <p className="text-justify text-sm leading-relaxed text-ink">
              {signal}
            </p>
            {subtext && (
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                {subtext}
              </p>
            )}
          </div>
          {hasCitations && (
            <div className="flex w-[30%] min-w-[7.5rem] shrink-0 justify-end">
              <CitationToggle
                open={open}
                count={sources!.length}
                onToggle={() => setOpen((v) => !v)}
              />
            </div>
          )}
        </div>
        {open && hasCitations && <CitationPanel sources={sources!} />}
      </div>
    );
  }

  if (!hasCitations) return null;

  return (
    <div className="mt-2">
      <CitationToggle
        open={open}
        count={sources!.length}
        onToggle={() => setOpen((v) => !v)}
      />
      {open && <CitationPanel sources={sources!} />}
    </div>
  );
}
