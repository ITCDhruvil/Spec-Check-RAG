"use client";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReactNode } from "react";

function safeHttpUrl(href: string | undefined): string | null {
  if (!href) return null;
  try {
    const url = new URL(href);
    if (url.protocol === "http:" || url.protocol === "https:") {
      return url.toString();
    }
  } catch {
    /* invalid */
  }
  return null;
}

const markdownComponents: Components = {
  h1: ({ children }) => (
    <h2 className="mb-2 mt-4 text-base font-semibold text-ink first:mt-0">{children}</h2>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 mt-4 text-sm font-semibold text-ink first:mt-0">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1.5 mt-3 text-sm font-semibold text-ink first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="mb-3 text-sm leading-relaxed text-ink last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-ink">{children}</ol>
  ),
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic text-ink-muted">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-accent/40 pl-3 text-sm italic text-ink-muted">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-surface-border" />,
  a: ({ href, children }) => {
    const safe = safeHttpUrl(href);
    if (!safe) return <span>{children}</span>;
    return (
      <a
        href={safe}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
      >
        {children}
      </a>
    );
  },
  img: ({ src, alt }) => {
    const safe = safeHttpUrl(typeof src === "string" ? src : undefined);
    if (!safe) return null;
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={safe}
        alt={alt ?? "Document figure"}
        className="my-3 max-h-80 max-w-full rounded-lg border border-surface-border bg-surface-muted/30 object-contain"
        loading="lazy"
      />
    );
  },
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto rounded-lg border border-surface-border">
      <table className="min-w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-muted/80">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-surface-border">{children}</tbody>,
  tr: ({ children }) => <tr className="divide-x divide-surface-border">{children}</tr>,
  th: ({ children }) => (
    <th className="px-3 py-2 font-semibold text-ink">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 align-top text-ink">{children}</td>
  ),
  code: ({ className, children }) => {
    const isBlock = Boolean(className);
    if (isBlock) {
      return (
        <pre className="mb-3 overflow-x-auto rounded-lg bg-surface-muted/80 p-3 text-xs">
          <code className={className}>{children}</code>
        </pre>
      );
    }
    return (
      <code className="rounded bg-surface-muted/80 px-1 py-0.5 text-xs text-ink">{children}</code>
    );
  },
};

export function MarkdownAssistantContent({ content }: { content: string }) {
  return (
    <div className="assistant-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** Inline bold/links for legacy plain-text paths (optional). */
export function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}
