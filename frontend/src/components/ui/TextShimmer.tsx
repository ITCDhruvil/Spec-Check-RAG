"use client";

/** Text shimmer (loading-ui/text-shimmer, CSS-only adaptation — no motion dep). */

export function TextShimmer({
  children,
  className = "",
  duration = 2,
}: {
  children: string;
  className?: string;
  duration?: number;
}) {
  const spread = Math.max(40, children.length * 2);
  return (
    <>
      <style>{`
        @keyframes text-shimmer-sweep {
          from { background-position: 100% center; }
          to { background-position: 0% center; }
        }
      `}</style>
      <span
        className={`relative inline-block bg-clip-text [-webkit-text-fill-color:transparent] ${className}`}
        style={{
          backgroundImage:
            `linear-gradient(90deg, transparent calc(50% - ${spread}px), currentColor, transparent calc(50% + ${spread}px)),` +
            `linear-gradient(color-mix(in oklab, currentColor 55%, transparent), color-mix(in oklab, currentColor 55%, transparent))`,
          backgroundSize: "250% 100%, auto",
          backgroundRepeat: "no-repeat, padding-box",
          animation: `text-shimmer-sweep ${duration}s linear infinite`,
        }}
      >
        {children}
      </span>
    </>
  );
}
