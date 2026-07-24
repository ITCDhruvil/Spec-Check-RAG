"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Modal } from "@/components/ui/Modal";
import {
  DotsVerticalIcon,
  KeyIcon,
  LoginArrowIcon,
  PowerIcon,
  TrashIcon,
} from "@/components/ui/icons";
import { deleteUser, updateUser } from "@/lib/api/auth";
import type { ManagedUser } from "@/lib/types/auth";

const MENU_WIDTH = 220;
const MENU_GAP = 4;

function IconButton({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <span
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
        tone === "danger"
          ? "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400"
          : "bg-surface-muted text-ink"
      }`}
    >
      {children}
    </span>
  );
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

/** "..." actions menu for a Users page row — mirrors DocumentActionsMenu. */
export function UserActionsMenu({
  user,
  currentUserId,
  onLoginAs,
  onSetPassword,
  loginAsBusy,
}: {
  user: ManagedUser;
  currentUserId?: number;
  onLoginAs: (user: ManagedUser) => void;
  onSetPassword: (user: ManagedUser) => void;
  loginAsBusy: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const toggleActive = useMutation({
    mutationFn: () => updateUser(user.id, { is_active: !user.is_active }),
    onSuccess: () => {
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const removeUser = useMutation({
    mutationFn: () => deleteUser(user.id),
    onSuccess: () => {
      setConfirmDelete(false);
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = () => {
    const anchor = buttonRef.current?.getBoundingClientRect();
    if (!anchor) return;
    const menuHeight = menuRef.current?.offsetHeight ?? 200;
    setCoords(computeMenuPosition(anchor, menuHeight));
  };

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open]);

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

  const canLoginAs = user.id !== currentUserId;

  const menu =
    open && coords && mounted ? (
      <div
        ref={menuRef}
        role="menu"
        style={{ top: coords.top, left: coords.left, width: MENU_WIDTH }}
        className="fixed z-[100] rounded-lg border border-surface-border bg-surface py-1 shadow-xl"
      >
        <ul className="py-0.5">
          {canLoginAs && (
            <li role="none">
              <button
                type="button"
                role="menuitem"
                disabled={!user.is_active || loginAsBusy}
                onClick={() => {
                  setOpen(false);
                  onLoginAs(user);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
              >
                <IconButton>
                  <LoginArrowIcon />
                </IconButton>
                <span>{loginAsBusy ? "Opening…" : "Login as"}</span>
              </button>
            </li>
          )}
          <li role="none">
            <button
              type="button"
              role="menuitem"
              disabled={user.is_admin || toggleActive.isPending}
              onClick={() => toggleActive.mutate()}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              <IconButton>
                <PowerIcon />
              </IconButton>
              <span>{user.is_active ? "Disable user" : "Enable user"}</span>
            </button>
          </li>
          <li role="none">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSetPassword(user);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink transition hover:bg-surface-muted"
            >
              <IconButton>
                <KeyIcon />
              </IconButton>
              <span>Change password</span>
            </button>
          </li>
          {!user.is_admin && (
            <li role="none" className="mt-0.5 border-t border-surface-border">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  setConfirmDelete(true);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
              >
                <IconButton tone="danger">
                  <TrashIcon />
                </IconButton>
                <span>Delete user</span>
              </button>
            </li>
          )}
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
        aria-label={`Actions for ${user.email}`}
      >
        <DotsVerticalIcon className="h-[18px] w-[18px]" />
      </button>

      {mounted && menu ? createPortal(menu, document.body) : null}

      <Modal
        open={confirmDelete}
        onClose={() => {
          if (!removeUser.isPending) setConfirmDelete(false);
        }}
        title="Delete user?"
        description={user.email}
      >
        <div className="space-y-4 px-2 pb-2 pt-1">
          <p className="text-sm leading-relaxed text-ink-muted">
            This permanently removes the account. This cannot be undone.
          </p>

          {removeUser.isError && (
            <p className="text-sm text-red-600 dark:text-red-300">
              {(removeUser.error as Error).message}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              disabled={removeUser.isPending}
              className="rounded-md border border-surface-border px-3 py-1.5 text-sm font-medium hover:bg-surface-muted disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => removeUser.mutate()}
              disabled={removeUser.isPending}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {removeUser.isPending ? "Deleting…" : "Delete permanently"}
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
