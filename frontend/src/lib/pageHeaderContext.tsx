"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export interface PageHeaderData {
  backHref: string;
  backLabel: string;
  title: string;
  subtitle?: string;
}

interface PageHeaderContextValue {
  header: PageHeaderData | null;
  setHeader: (data: PageHeaderData | null) => void;
}

const PageHeaderContext = createContext<PageHeaderContextValue>({
  header: null,
  setHeader: () => {},
});

export function PageHeaderProvider({ children }: { children: ReactNode }) {
  const [header, setHeader] = useState<PageHeaderData | null>(null);

  return (
    <PageHeaderContext.Provider value={{ header, setHeader }}>
      {children}
    </PageHeaderContext.Provider>
  );
}

/** Read the header registered by the current page (used by AppShell). */
export function usePageHeaderData() {
  return useContext(PageHeaderContext).header;
}

/** Register page header info to render in the app top bar while mounted. */
export function usePageHeader(data: PageHeaderData) {
  const { setHeader } = useContext(PageHeaderContext);
  const { backHref, backLabel, title, subtitle } = data;

  useEffect(() => {
    setHeader({ backHref, backLabel, title, subtitle });
    return () => setHeader(null);
  }, [setHeader, backHref, backLabel, title, subtitle]);
}
