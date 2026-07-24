"use client";

import { useEffect, useId } from "react";

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  blurBackdrop = false,
  maxWidth = "max-w-sm",
}: {
  open: boolean;
  onClose: () => void;
  /** Omit to render children without the built-in header. */
  title?: string;
  description?: string;
  children: React.ReactNode;
  /** Blur the page behind the dialog. */
  blurBackdrop?: boolean;
  /** Tailwind max-width class for the dialog. */
  maxWidth?: string;
}) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <button
        type="button"
        className={`absolute inset-0 bg-ink/40 ${blurBackdrop ? "backdrop-blur-sm" : ""}`}
        aria-label="Close dialog"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative z-10 w-full ${maxWidth} rounded-lg border border-surface-border bg-surface shadow-xl`}
      >
        {title && (
          <div className="border-b border-surface-border px-4 py-3">
            <h2 id={titleId} className="text-sm font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 truncate text-xs text-ink-muted">{description}</p>
            )}
          </div>
        )}
        <div className="p-2">{children}</div>
      </div>
    </div>
  );
}
