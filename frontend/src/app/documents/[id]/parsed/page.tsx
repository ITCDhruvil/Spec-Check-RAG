"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  getParsedDocument,
  getParsingStatus,
  listParsedPages,
  listParsedSections,
} from "@/lib/api/parsing";
import type { PipelineStage } from "@/lib/types/document";

function qualityLabel(score: number): string {
  if (score >= 0.85) return "High";
  if (score >= 0.6) return "Medium";
  return "Low";
}

function qualityClass(score: number): string {
  if (score >= 0.85) return "text-emerald-700 bg-emerald-50";
  if (score >= 0.6) return "text-amber-800 bg-amber-50";
  return "text-red-800 bg-red-50";
}

export default function ParsedDocumentPage() {
  const params = useParams();
  const documentId = String(params.id);
  const [selectedPage, setSelectedPage] = useState(1);

  const statusQuery = useQuery({
    queryKey: ["parsing-status", documentId],
    queryFn: () => getParsingStatus(documentId),
    refetchInterval: (q) => {
      const ps = q.state.data?.parsing_status;
      if (ps === "completed" || ps === "failed") return false;
      return 3000;
    },
  });

  const parsedQuery = useQuery({
    queryKey: ["parsed-document", documentId],
    queryFn: () => getParsedDocument(documentId),
    enabled: statusQuery.data?.parsing_status === "completed",
  });

  const pagesQuery = useQuery({
    queryKey: ["parsed-pages", documentId],
    queryFn: () => listParsedPages(documentId),
    enabled: statusQuery.data?.parsing_status === "completed",
  });

  const sectionsQuery = useQuery({
    queryKey: ["parsed-sections", documentId],
    queryFn: () => listParsedSections(documentId),
    enabled: statusQuery.data?.parsing_status === "completed",
  });

  const docStatus = statusQuery.data?.document_status as PipelineStage | undefined;
  const parsingStatus = statusQuery.data?.parsing_status;
  const quality = statusQuery.data?.parsing_quality_score ?? 0;
  const pages = pagesQuery.data ?? [];
  const selected = pages.find((p) => p.page_number === selectedPage) ?? pages[0];

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`/documents/${documentId}`}
          className="text-xs text-ink-muted hover:text-ink"
        >
          ← Document details
        </Link>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          Parsed content
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Structure preview for summarization (Phase 2 — no AI yet).
        </p>
      </div>

      <section className="grid gap-4 rounded-lg border border-surface-border bg-surface p-5 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-xs text-ink-muted">Document status</p>
          {docStatus ? <StatusBadge status={docStatus} /> : <span>—</span>}
        </div>
        <div>
          <p className="text-xs text-ink-muted">Parsing status</p>
          <p className="mt-1 text-sm font-medium capitalize">
            {parsingStatus ?? "pending"}
          </p>
        </div>
        <div>
          <p className="text-xs text-ink-muted">Pages</p>
          <p className="mt-1 text-sm font-medium">
            {statusQuery.data?.total_pages ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-ink-muted">Quality</p>
          {parsingStatus === "completed" ? (
            <span
              className={`mt-1 inline-block rounded px-2 py-0.5 text-xs font-medium ${qualityClass(quality)}`}
            >
              {qualityLabel(quality)} ({(quality * 100).toFixed(0)}%)
            </span>
          ) : (
            <p className="mt-1 text-sm">—</p>
          )}
        </div>
        <div>
          <p className="text-xs text-ink-muted">OCR pages</p>
          <p className="mt-1 text-sm font-medium">
            {statusQuery.data?.ocr_pages ?? 0}
          </p>
        </div>
      </section>

      {parsingStatus !== "completed" && (
        <div className="rounded-lg border border-surface-border bg-surface p-6 text-sm text-ink-muted">
          {statusQuery.isLoading
            ? "Loading parsing status…"
            : "Parsing in progress or not started. This view updates automatically."}
        </div>
      )}

      {parsedQuery.data && (
        <section className="rounded-lg border border-surface-border bg-surface p-5">
          <h3 className="text-sm font-semibold">Structured preview</h3>
          <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-surface-muted p-3 text-xs whitespace-pre-wrap">
            {parsedQuery.data.structured_text_preview || "(empty)"}
          </pre>
        </section>
      )}

      {sectionsQuery.data && sectionsQuery.data.length > 0 && (
        <section className="rounded-lg border border-surface-border bg-surface p-5">
          <h3 className="text-sm font-semibold">Sections ({sectionsQuery.data.length})</h3>
          <ul className="mt-4 divide-y divide-surface-border">
            {sectionsQuery.data.map((section) => (
              <li key={section.id} className="py-3">
                <p className="text-sm font-medium">
                  {section.section_order + 1}. {section.title}
                </p>
                <p className="mt-1 text-xs text-ink-muted">
                  Pages {section.page_start}–{section.page_end} ·{" "}
                  {section.content.length} chars
                </p>
                <pre className="mt-2 max-h-32 overflow-auto rounded bg-surface-muted p-2 text-xs whitespace-pre-wrap">
                  {section.content.slice(0, 800)}
                  {section.content.length > 800 ? "…" : ""}
                </pre>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pages.length > 0 && (
        <section className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-surface-border bg-surface p-4 lg:col-span-1">
            <h3 className="text-sm font-semibold">Pages</h3>
            <ul className="mt-3 max-h-96 space-y-1 overflow-auto">
              {pages.map((page) => (
                <li key={page.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedPage(page.page_number)}
                    className={`w-full rounded px-2 py-1.5 text-left text-xs ${
                      selectedPage === page.page_number
                        ? "bg-accent/10 text-accent"
                        : "hover:bg-surface-muted"
                    }`}
                  >
                    Page {page.page_number}
                    {page.ocr_used && (
                      <span className="ml-1 text-ink-muted">(OCR)</span>
                    )}
                    <span className="float-right text-ink-muted">
                      {(page.quality_score * 100).toFixed(0)}%
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-lg border border-surface-border bg-surface p-4 lg:col-span-2">
            <h3 className="text-sm font-semibold">
              Page {selected?.page_number} text
            </h3>
            {selected && (
              <dl className="mt-2 flex flex-wrap gap-4 text-xs text-ink-muted">
                <div>
                  Method: <span className="text-ink">{selected.extraction_method}</span>
                </div>
                <div>
                  OCR: <span className="text-ink">{selected.ocr_used ? "Yes" : "No"}</span>
                </div>
                <div>
                  Quality:{" "}
                  <span className="text-ink">
                    {(selected.quality_score * 100).toFixed(1)}%
                  </span>
                </div>
              </dl>
            )}
            <pre className="mt-3 max-h-[28rem] overflow-auto rounded-md bg-surface-muted p-3 text-xs whitespace-pre-wrap">
              {selected?.extracted_text || "(no text on this page)"}
            </pre>
          </div>
        </section>
      )}
    </div>
  );
}
