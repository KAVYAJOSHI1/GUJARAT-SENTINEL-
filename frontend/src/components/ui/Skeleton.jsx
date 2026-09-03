// Shimmer skeleton loader (README §7 UI States / §21 Day-4).
export function Skeleton({ width = "100%", height = 14, radius = 4, style }) {
  return (
    <span
      className="skeleton"
      style={{ display: "inline-block", width, height, borderRadius: radius, ...style }}
    />
  );
}

export function SkeletonCard({ height = 120 }) {
  return <Skeleton height={height} radius={6} style={{ display: "block" }} />;
}

export function SkeletonRows({ rows = 4, height = 40, gap = 8 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={height} radius={4} style={{ display: "block" }} />
      ))}
    </div>
  );
}
