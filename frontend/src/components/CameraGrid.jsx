import { VideoOff } from "lucide-react";
import CameraCard from "./CameraCard.jsx";
import EmptyState from "./ui/EmptyState.jsx";
import { SkeletonCard } from "./ui/Skeleton.jsx";

// Responsive camera preview grid (README §4.3 — "2x2 and 3x3 video preview
// cards"). `columns` picks the layout density; CSS handles the responsive
// collapse on narrow viewports.
export default function CameraGrid({
  cameras = [],
  columns = 3,
  loading = false,
  selectedId,
  onSelect,
  skeletonCount = 6,
}) {
  const className = columns >= 4 ? "camera-grid-4" : "camera-grid-3";

  if (loading) {
    return (
      <div className={className}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <SkeletonCard key={i} height={132} />
        ))}
      </div>
    );
  }

  if (!cameras.length) {
    return <EmptyState icon={VideoOff} title="No active camera feeds found" hint="Check the ingestion service or backend connection." />;
  }

  return (
    <div className={className}>
      {cameras.map((cam) => (
        <CameraCard
          key={cam.id}
          cam={cam}
          selected={selectedId === cam.id}
          onClick={onSelect}
        />
      ))}
    </div>
  );
}
