"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

/** Technical document page — redirect end users to the briefing view. */
export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = String(params.id);

  useEffect(() => {
    router.replace(`/documents/${id}/summary`);
  }, [id, router]);

  return (
    <p className="text-sm text-ink-muted">Opening your specification briefing…</p>
  );
}
