export function SummaryContentBox({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-surface-border bg-surface-muted/50 px-4 py-3 ${className}`.trim()}
    >
      {children}
    </div>
  );
}
