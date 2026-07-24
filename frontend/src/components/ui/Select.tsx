"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ChevronDownIcon } from "@/components/ui/icons";

type SelectOption<T extends string> = { value: T; label: string };

type MenuCoords = { top: number; left: number; width: number };

function computeMenuPosition(anchor: DOMRect, menuHeight: number): MenuCoords {
  let top = anchor.bottom + 4;
  if (top + menuHeight > window.innerHeight - 8) {
    top = Math.max(8, anchor.top - menuHeight - 4);
  }
  return { top, left: anchor.left, width: anchor.width };
}

/**
 * Custom-styled single-select dropdown — replaces the browser's native
 * <select>, whose popup can't be themed (it always renders with the OS
 * light-mode chrome regardless of our dark mode).
 */
export function Select<T extends string>({
  value,
  onChange,
  options,
  disabled,
  title,
  className = "",
  menuClassName = "",
}: {
  value: T;
  onChange: (value: T) => void;
  options: SelectOption<T>[];
  disabled?: boolean;
  title?: string;
  className?: string;
  menuClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const updatePosition = () => {
    const anchor = buttonRef.current?.getBoundingClientRect();
    if (!anchor) return;
    const menuHeight = menuRef.current?.offsetHeight ?? options.length * 32 + 8;
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
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) return;
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

  const selected = options.find((o) => o.value === value);

  const menu =
    open && coords && mounted ? (
      <div
        ref={menuRef}
        role="listbox"
        style={{ top: coords.top, left: coords.left, minWidth: coords.width }}
        className={`fixed z-[100] max-h-60 overflow-auto rounded-lg border border-surface-border bg-surface py-1 shadow-xl ${menuClassName}`}
      >
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="option"
            aria-selected={option.value === value}
            onClick={() => {
              onChange(option.value);
              setOpen(false);
            }}
            className={`flex w-full items-center px-3 py-1.5 text-left text-xs transition ${
              option.value === value
                ? "bg-accent/10 font-medium text-accent"
                : "text-ink hover:bg-surface-muted"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    ) : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        title={title}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`inline-flex items-center gap-1 rounded border border-surface-border bg-surface px-1.5 py-0.5 text-xs text-ink-muted transition hover:bg-surface-muted disabled:opacity-50 ${className}`}
      >
        <span className="truncate">{selected?.label ?? "Select…"}</span>
        <ChevronDownIcon className="h-3 w-3 shrink-0" />
      </button>

      {mounted && menu ? createPortal(menu, document.body) : null}
    </>
  );
}
