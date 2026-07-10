"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

import { normalizeHighlightTarget } from "@/lib/citationUtils";

export interface CitationHighlightTarget {
  page: number;
  sourceText?: string;
}

interface PdfNavigationContextValue {
  activePage: number | null;
  activeHighlight: CitationHighlightTarget | null;
  /** All spans to highlight for the active field (multi-source citations). */
  activeHighlights: CitationHighlightTarget[];
  flashKey: number;
  canJump: boolean;
  applyHighlight: (target: CitationHighlightTarget) => CitationHighlightTarget | null;
  jumpToCitation: (target: CitationHighlightTarget) => void;
  /** Jump to the first span, highlight all spans of a multi-source field. */
  jumpToCitations: (targets: CitationHighlightTarget[]) => void;
  setActiveHighlights: (targets: CitationHighlightTarget[]) => void;
  setCanJump: (value: boolean) => void;
  registerScrollToCitation: (fn: (target: CitationHighlightTarget) => void) => void;
  unregisterScrollToCitation: () => void;
  /** Register a callback that expands the (collapsible) preview panel. */
  registerExpandPreview: (fn: () => void) => void;
  unregisterExpandPreview: () => void;
  previewContainerRef: React.RefObject<HTMLDivElement | null>;
}

const PdfNavigationContext = createContext<PdfNavigationContextValue>({
  activePage: null,
  activeHighlight: null,
  activeHighlights: [],
  flashKey: 0,
  canJump: false,
  applyHighlight: () => null,
  jumpToCitation: () => {},
  jumpToCitations: () => {},
  setActiveHighlights: () => {},
  setCanJump: () => {},
  registerScrollToCitation: () => {},
  unregisterScrollToCitation: () => {},
  registerExpandPreview: () => {},
  unregisterExpandPreview: () => {},
  previewContainerRef: { current: null },
});

export function PdfNavigationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [activePage, setActivePage] = useState<number | null>(null);
  const [activeHighlight, setActiveHighlight] =
    useState<CitationHighlightTarget | null>(null);
  const [activeHighlights, setActiveHighlights] = useState<
    CitationHighlightTarget[]
  >([]);
  const [flashKey, setFlashKey] = useState(0);
  const [canJump, setCanJump] = useState(false);
  const previewContainerRef = useRef<HTMLDivElement | null>(null);
  const scrollToCitationRef = useRef<
    ((target: CitationHighlightTarget) => void) | null
  >(null);
  const expandPreviewRef = useRef<(() => void) | null>(null);
  // Set when a jump is requested while the preview (and its navigator) is not
  // yet mounted — e.g. the panel was collapsed. Drained once the navigator
  // registers, so an expand-then-jump lands on the right page.
  const pendingJumpRef = useRef<CitationHighlightTarget | null>(null);

  const registerScrollToCitation = useCallback(
    (fn: (target: CitationHighlightTarget) => void) => {
      scrollToCitationRef.current = fn;
      const pending = pendingJumpRef.current;
      if (pending) {
        pendingJumpRef.current = null;
        fn(pending);
      }
    },
    []
  );

  const unregisterScrollToCitation = useCallback(() => {
    scrollToCitationRef.current = null;
  }, []);

  const registerExpandPreview = useCallback((fn: () => void) => {
    expandPreviewRef.current = fn;
  }, []);

  const unregisterExpandPreview = useCallback(() => {
    expandPreviewRef.current = null;
  }, []);

  const applyHighlight = useCallback((target: CitationHighlightTarget) => {
    const normalized = normalizeHighlightTarget(target);
    if (!normalized) return null;
    setActivePage(normalized.page);
    setActiveHighlight(normalized);
    setFlashKey((k) => k + 1);
    return normalized;
  }, []);

  /** Scroll to an anchor now if the navigator is mounted, else queue it. */
  const dispatchJump = useCallback((anchor: CitationHighlightTarget) => {
    // Expand a collapsed preview so it (re)mounts and registers its navigator.
    expandPreviewRef.current?.();
    previewContainerRef.current?.scrollIntoView({
      behavior: "auto",
      block: "nearest",
    });
    if (scrollToCitationRef.current) {
      scrollToCitationRef.current(anchor);
    } else {
      // Preview not mounted yet (was collapsed) — run once it registers.
      pendingJumpRef.current = anchor;
    }
  }, []);

  const jumpToCitation = useCallback(
    (target: CitationHighlightTarget) => {
      const normalized = normalizeHighlightTarget(target);
      if (!normalized) return;
      setActiveHighlights([normalized]);
      dispatchJump(normalized);
    },
    [dispatchJump]
  );

  const jumpToCitations = useCallback(
    (targets: CitationHighlightTarget[]) => {
      const normalized = targets
        .map((t) => normalizeHighlightTarget(t))
        .filter((t): t is CitationHighlightTarget => t !== null);
      if (!normalized.length) return;

      // Highlight every span at once; scroll anchors on the first.
      setActiveHighlights(normalized);
      dispatchJump(normalized[0]);
    },
    [dispatchJump]
  );

  const value = useMemo(
    () => ({
      activePage,
      activeHighlight,
      activeHighlights,
      flashKey,
      canJump,
      applyHighlight,
      jumpToCitation,
      jumpToCitations,
      setActiveHighlights,
      setCanJump,
      registerScrollToCitation,
      unregisterScrollToCitation,
      registerExpandPreview,
      unregisterExpandPreview,
      previewContainerRef,
    }),
    [
      activePage,
      activeHighlight,
      activeHighlights,
      flashKey,
      canJump,
      applyHighlight,
      jumpToCitation,
      jumpToCitations,
      registerScrollToCitation,
      unregisterScrollToCitation,
      registerExpandPreview,
      unregisterExpandPreview,
    ]
  );

  return (
    <PdfNavigationContext.Provider value={value}>
      {children}
    </PdfNavigationContext.Provider>
  );
}

export function usePdfNavigation() {
  return useContext(PdfNavigationContext);
}
