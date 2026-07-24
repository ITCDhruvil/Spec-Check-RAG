/** Spokes loading spinner (loading-ui/spokes, adapted — no shadcn deps). */

export function Spokes({
  className = "h-5 w-5",
  size = 24,
  style,
  ...props
}: React.ComponentProps<"svg"> & { size?: number }) {
  return (
    <>
      <style>{`
        @keyframes loading-ui-spokes-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <svg
        viewBox="0 0 24 24"
        // Intrinsic fallback size: CSS classes (h-5 w-5 etc.) override these
        // attributes when present; without them a missing utility class would
        // render a full-screen spinner.
        width={size}
        height={size}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        style={{
          animationName: "loading-ui-spokes-spin",
          animationDuration: "var(--duration, 1s)",
          animationTimingFunction: "linear",
          animationIterationCount: "infinite",
          ...style,
        }}
        aria-hidden
        {...props}
      >
        <path
          d="M12 2V6M16.2 7.8L19.1 4.9M18 12H22M16.2 16.2L19.1 19.1M12 18V22M4.9 19.1L7.8 16.2M2 12H6M4.9 4.9L7.8 7.8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </>
  );
}

/** Full-area centered loader for page/section loading states.
 * Layout uses inline styles so centering survives even if utility CSS
 * has not loaded yet (this renders during app bootstrap). */
export function SpokesLoader({
  label,
  className = "py-12",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "8px",
        width: "100%",
      }}
    >
      <Spokes className="h-6 w-6 text-ink-muted dark:text-accent" size={24} />
      {label && <p className="text-sm text-ink-muted">{label}</p>}
    </div>
  );
}
