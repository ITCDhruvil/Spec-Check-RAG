"use client";

import { useState } from "react";

import { CitationPanel, CitationToggle } from "@/components/summary/SourceCitationList";
import { MarkdownAssistantContent } from "@/components/chat/MarkdownAssistantContent";
import type { SourceCitation } from "@/lib/types/intelligence";

function CopyIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <rect x="5" y="5" width="8" height="8" rx="1" />
      <path d="M5 11H4a2 2 0 01-2-2V4a2 2 0 012-2h5a2 2 0 012 2v1" />
    </svg>
  );
}

export function AssistantMessageBubble({
  content,
  sources,
}: {
  content: string;
  sources: SourceCitation[];
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="w-full max-w-none rounded-xl border border-surface-border bg-surface px-4 py-4 shadow-sm">
      <MarkdownAssistantContent content={content} />

      {sourcesOpen && sources.length > 0 && (
        <div className="mt-4 border-t border-surface-border pt-4">
          <CitationPanel sources={sources} />
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-surface-border pt-3">
        <button
          type="button"
          onClick={handleCopy}
          title={copied ? "Copied" : "Copy answer"}
          aria-label={copied ? "Copied" : "Copy answer"}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-surface-border text-ink-muted transition hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
        >
          <CopyIcon />
        </button>

        {sources.length > 0 && (
          <CitationToggle
            open={sourcesOpen}
            count={sources.length}
            onToggle={() => setSourcesOpen((v) => !v)}
          />
        )}
      </div>
    </div>
  );
}
