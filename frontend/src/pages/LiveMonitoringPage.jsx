import { useMemo, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Grid2x2, Grid3x3, LayoutGrid, Video } from "lucide-react";
import { C } from "../theme.js";
import CameraPlayer from "../components/camera/CameraPlayer.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import { Badge, CommandButton, Panel, SectionHeader } from "../components/ui/primitives.jsx";
import { fmtRelative } from "../utils/datetime.js";

const LAYOUTS = [
  { n: 1, label: "1×1", icon: Video }, { n: 2, label: "2×2", icon: Grid2x2 },
  { n: 3, label: "3×3", icon: Grid3x3 }, { n: 4, label: "4×4", icon: LayoutGrid },
];

// Phase 16F — multi-camera investigation wall. Uses the existing
// CameraPlayer (honest LIVE/RECORDED/OFFLINE modes). No fake live streams.
export default function LiveMonitoringPage() {
  const nav = useNavigate();
  const { cameras = [] } = useOutletContext();
  const [grid, setGrid] = useState(2);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return cameras.filter((c) => !t || `${c.code} ${c.name} ${c.locationDesc || ""}`.toLowerCase().includes(t));
  }, [cameras, q]);

  const perPage = grid * grid;
  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const shown = filtered.slice(page * perPage, page * perPage + perPage);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Live Monitoring Wall</span>
        <span style={{ color: C.muted, fontSize: 11 }}>{filtered.length} cameras · honest playback state</span>
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="filter cameras…"
          style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 9px", fontSize: 11, marginLeft: "auto" }} />
        <div style={{ display: "flex", gap: 4 }}>
          {LAYOUTS.map((l) => (
            <button key={l.n} onClick={() => { setGrid(l.n); setPage(0); }}
              style={{ background: grid === l.n ? C.accentGlow : "transparent", border: `1px solid ${grid === l.n ? C.accent : C.border}`, color: grid === l.n ? C.accent : C.muted, borderRadius: 4, padding: "4px 8px", fontSize: 10, fontWeight: 700, cursor: "pointer" }}>
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {pages > 1 && (
        <div style={{ display: "flex", gap: 6, marginBottom: 10, alignItems: "center" }}>
          <CommandButton small disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</CommandButton>
          <span style={{ color: C.muted, fontSize: 11 }}>page {page + 1} / {pages}</span>
          <CommandButton small disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>Next</CommandButton>
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState icon={Video} title="No cameras" hint="Adjust the filter." />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${grid}, 1fr)`, gap: 10 }}>
          {shown.map((c) => (
            <Panel key={c.uuid || c.id}>
              <SectionHeader title={c.code || c.id}
                sub={c.locationDesc || c.name}
                right={<CommandButton small onClick={() => nav(`/camera-intelligence/${c.code}`)}>Open</CommandButton>} />
              <div style={{ padding: 8 }}>
                <CameraPlayer cameraId={c.uuid || c.id} height={grid === 1 ? 420 : grid === 2 ? 240 : 170} />
              </div>
              <div style={{ padding: "4px 10px 8px", display: "flex", gap: 8, fontSize: 9.5, color: C.muted, flexWrap: "wrap" }}>
                <span>FPS {c.fps ?? "—"}</span>
                <span>{c.lastDetectionAt ? `det ${fmtRelative(c.lastDetectionAt)}` : "no detections"}</span>
                {c.status && <Badge color={c.status === "active" ? C.green : c.status === "offline" ? C.red : C.amber}>{c.status}</Badge>}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
