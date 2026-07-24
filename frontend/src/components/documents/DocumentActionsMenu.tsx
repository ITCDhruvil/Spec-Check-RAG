"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { AdminNotePanel } from "@/components/summary/AdminNotePanel";
import { Modal } from "@/components/ui/Modal";
import { deleteDocument } from "@/lib/api/documents";
import { truncateFilename } from "@/lib/truncate";
import type { DocumentListItem } from "@/lib/types/document";

const MENU_WIDTH = 240;
const MENU_GAP = 4;

function IconButton({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-muted text-ink">
      {children}
    </span>
  );
}

function DotsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="12" cy="5" r="1.75" />
      <circle cx="12" cy="12" r="1.75" />
      <circle cx="12" cy="19" r="1.75" />
    </svg>
  );
}

function SummaryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
      <path d="M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
    </svg>
  );
}

function NoteIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M11 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-5" />
      <path d="M18.5 2.5a2.1 2.1 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
    </svg>
  );
}

type LinkAction = {
  kind: "link";
  label: string;
  href: string;
  icon: React.ReactNode;
};

function buildLinkActions(doc: DocumentListItem): LinkAction[] {
  const isReady = doc.status === "completed";
  const base = `/documents/${doc.id}`;
  const actions: LinkAction[] = [
    {
      kind: "link",
      label: isReady ? "View briefing" : "View status",
      href: `${base}/summary`,
      icon: <SummaryIcon />,
    },
  ];

  if (isReady) {
    actions.push({
      kind: "link",
      label: "Manual search",
      href: `${base}/manual`,
      icon: <SearchIcon />,
    });
  }

  // Temporarily hidden from UI; keep chat route available to re-enable.
  const SHOW_ASK_QUESTIONS = false;
  if (SHOW_ASK_QUESTIONS && isReady) {
    actions.push({
      kind: "link",
      label: "Ask questions",
      href: `${base}/chat`,
      icon: <ChatIcon />,
    });
  }

  return actions;
}

type MenuCoords = { top: number; left: number };

function computeMenuPosition(anchor: DOMRect, menuHeight: number): MenuCoords {
  let top = anchor.bottom + MENU_GAP;
  let left = anchor.right - MENU_WIDTH;

  if (top + menuHeight > window.innerHeight - 8) {
    top = Math.max(8, anchor.top - menuHeight - MENU_GAP);
  }
  if (left < 8) left = 8;
  if (left + MENU_WIDTH > window.innerWidth - 8) {
    left = window.innerWidth - MENU_WIDTH - 8;
  }

  return { top, left };
}

export function DocumentActionsMenu({ doc }: { doc: DocumentListItem }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const linkActions = buildLinkActions(doc);

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocument(doc.id),
    onSuccess: () => {
      setConfirmDelete(false);
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = () => {
    const anchor = buttonRef.current?.getBoundingClientRect();
    if (!anchor) return;
    const menuHeight = menuRef.current?.offsetHeight ?? 220;
    setCoords(computeMenuPosition(anchor, menuHeight));
  };

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, linkActions.length]);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onReposition = () => updatePosition();

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);

    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open]);

  const openDeleteConfirm = () => {
    setOpen(false);
    setConfirmDelete(true);
  };

  const menu =
    open && coords && mounted ? (
      <div
        ref={menuRef}
        role="menu"
        style={{ top: coords.top, left: coords.left, width: MENU_WIDTH }}
        className="fixed z-[100] rounded-lg border border-surface-border bg-surface py-1 shadow-xl"
      >
        <p
          className="border-b border-surface-border px-3 py-2 text-xs font-medium text-ink-muted"
          title={doc.original_filename}
        >
          <span className="line-clamp-2">{doc.original_filename}</span>
        </p>
        <ul className="py-0.5">
          {linkActions.map((action) => (
            <li key={action.href + action.label} role="none">
              <Link
                href={action.href}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2 text-sm text-ink transition hover:bg-surface-muted"
              >
                <IconButton>{action.icon}</IconButton>
                <span>{action.label}</span>
              </Link>
            </li>
          ))}
          <li role="none">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setNoteOpen(true);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink transition hover:bg-surface-muted"
            >
              <IconButton>
                <NoteIcon />
              </IconButton>
              <span>Admin note</span>
            </button>
          </li>
          <li role="none" className="mt-0.5 border-t border-surface-border">
            <button
              type="button"
              role="menuitem"
              onClick={openDeleteConfirm}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400">
                <TrashIcon />
              </span>
              <span>Delete document</span>
            </button>
          </li>
        </ul>
      </div>
    ) : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={`inline-flex h-8 w-8 items-center justify-center rounded-md transition ${
          open
            ? "bg-surface-muted text-ink"
            : "text-ink-muted hover:bg-surface-muted hover:text-ink"
        }`}
        aria-label={`Actions for ${doc.original_filename}`}
      >
        <DotsIcon />
      </button>

      {mounted && menu ? createPortal(menu, document.body) : null}

      <Modal
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        blurBackdrop
        maxWidth="max-w-2xl"
      >
        <div className="px-3 pb-3 pt-3">
          {noteOpen && (
            <AdminNotePanel
              documentId={doc.id}
              bare
              docName={truncateFilename(doc.tender_title || doc.original_filename, 48)}
            />
          )}
        </div>
      </Modal>

      <Modal
        open={confirmDelete}
        onClose={() => {
          if (!deleteMutation.isPending) setConfirmDelete(false);
        }}
        title="Delete document?"
        description={doc.original_filename}
      >
        <div className="space-y-4 px-2 pb-2 pt-1">
          <p className="text-sm leading-relaxed text-ink-muted">
            This permanently removes the file, specification briefing, chat history,
            and all analysis for this document. This cannot be undone.
          </p>

          {deleteMutation.isError && (
            <p className="text-sm text-red-600 dark:text-red-300">
              {(deleteMutation.error as Error).message}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              disabled={deleteMutation.isPending}
              className="rounded-md border border-surface-border px-3 py-1.5 text-sm font-medium hover:bg-surface-muted disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete permanently"}
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
