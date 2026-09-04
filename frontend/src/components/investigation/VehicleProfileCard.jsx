import { Calendar, Camera, Clock, Hourglass, MapPin, ShieldAlert } from "lucide-react";
import { C } from "../../theme.js";
import { formatPlate } from "../../utils/plate.js";

// Vehicle Profile Summary Card (DEVELOPER_README §14.5 / §3):
// First Seen, Last Seen, Total Sightings, Camera Count, Journey Duration,
// Watchlist status.
const fmt = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
};

// "15m 45s" / "2h 05m" / "3d 4h" -- always from real first/last timestamps,
// never fabricated (single-sighting journeys just show "—").
function formatDuration(firstIso, lastIso) {
  if (!firstIso || !lastIso) return "—";
  const start = new Date(firstIso).getTime();
  const end = new Date(lastIso).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const totalSec = Math.round((end - start) / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${String(mins).padStart(2, "0")}m`;
  return `${mins}m ${String(secs).padStart(2, "0")}s`;
}

function Metric({ icon: Icon, label, value, color = C.text }) {
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 14px", flex: "1 1 150px" }}>
      <div style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1.1, display: "flex", alignItems: "center", gap: 5, marginBottom: 5 }}>
        <Icon size={11} /> {label}
      </div>
      <div style={{ color, fontSize: 16, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{value}</div>
    </div>
  );
}

export default function VehicleProfileCard({ result }) {
  if (!result) return null;
  const { plate, totalSightings, cameraCount, firstSeen, lastSeen, watchlistHit } = result;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
        <div style={{ fontFamily: "'Space Mono', monospace", fontSize: 20, fontWeight: 700, color: C.text, letterSpacing: 1.5 }}>
          {formatPlate(plate)}
        </div>
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            background: watchlistHit ? C.redGlow : C.greenGlow,
            border: `1px solid ${watchlistHit ? C.red : C.green}55`,
            color: watchlistHit ? C.red : C.green,
            borderRadius: 4,
            padding: "4px 10px",
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 1,
          }}
        >
          <ShieldAlert size={12} /> {watchlistHit ? "Active watchlist hit" : "No watchlist hit"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Metric icon={MapPin} label="Total sightings" value={totalSightings} color={C.accent} />
        <Metric icon={Camera} label="Cameras" value={cameraCount} />
        <Metric icon={Calendar} label="First seen" value={fmt(firstSeen)} />
        <Metric icon={Clock} label="Last seen" value={fmt(lastSeen)} />
        <Metric icon={Hourglass} label="Journey duration" value={formatDuration(firstSeen, lastSeen)} color={C.violet} />
      </div>
    </div>
  );
}
