export function Pagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(page, totalPages);
  const start = totalItems === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const end = Math.min(safePage * pageSize, totalItems);

  if (totalItems <= pageSize) {
    return (
      <p className="text-xs text-ink-muted">
        {totalItems === 0
          ? "No results"
          : `Showing ${totalItems} document${totalItems === 1 ? "" : "s"}`}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-ink-muted">
        Showing {start}–{end} of {totalItems}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
          className="rounded-md border border-surface-border bg-surface px-3 py-1.5 text-xs font-medium text-ink disabled:cursor-not-allowed disabled:opacity-40 hover:bg-surface-muted"
        >
          Previous
        </button>
        <span className="min-w-[5rem] text-center text-xs tabular-nums text-ink-muted">
          Page {safePage} of {totalPages}
        </span>
        <button
          type="button"
          disabled={safePage >= totalPages}
          onClick={() => onPageChange(safePage + 1)}
          className="rounded-md border border-surface-border bg-surface px-3 py-1.5 text-xs font-medium text-ink disabled:cursor-not-allowed disabled:opacity-40 hover:bg-surface-muted"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function paginateSlice<T>(items: T[], page: number, pageSize: number): T[] {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
