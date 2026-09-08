import { useMemo, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Grid2x2, Grid3x3, LayoutGrid, Video, Crosshair } from "lucide-react";
import { C } from "../theme.js";
import CameraPlayer from "../components/camera/CameraPlayer.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import { Badge, CommandButton, Panel, SectionHeader } from "../components/ui/primitives.jsx";

const LAYOUTS = [
  { n: 1, label: "1×1", icon: Video }, { n: 2, label: "2×2", icon: Grid2x2 },
  { n: 3, label: "3×3", icon: Grid3x3 }, { n: 4, label: "4×4", icon: LayoutGrid },
];

// Phase 16F — multi-camera investigation wall. Uses the existing
// CameraPlayer (honest LIVE / DEGRADED / RECORDED / OFFLINE modes). No fake
// live streams — a snapshot is never presented as live video.
export default function LiveMonitoringPage() {
  const nav = useNavigate();
  const { cameras = [], latestDetectionByCamera = {}, detectionCountByCamera = {} } = useOutletContext();
  const [grid, setGrid] = useState(2);
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [onlyAlerts, setOnlyAlerts] = useState(false);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return cameras.filter((c) => {
      if (onlyAlerts && c.status !== "alert") return false;
      return !t || `${c.code} ${c.name} ${c.locationDesc || ""}`.toLowerCase().includes(t);
    });
  }, [cameras, q, onlyAlerts]);

  const perPage = grid * grid;
  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const shown = filtered.slice(page * perPage, page * perPage + perPage);
  const alertCount = cameras.filter((c) => c.status === "alert").length;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Live Monitoring Wall</span>
        <span style={{ color: C.muted, fontSize: 11 }}>{filtered.length} cameras · honest playback state</span>
        <button onClick={() => { setOnlyAlerts((v) => !v); setPage(0); }}
          style={{ background: onlyAlerts ? C.red : "transparent", border: `1px solid ${onlyAlerts ? C.red : C.border}`, color: onlyAlerts ? "#0b0f14" : C.muted, borderRadius: 4, padding: "4px 9px", fontSize: 10, fontWeight: 700, cursor: "pointer" }}>
          ⚠ ALERTS ONLY ({alertCount})
        </button>
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
        <EmptyState icon={Video} title="No cameras" hint={onlyAlerts ? "No cameras with an active alert." : "Adjust the filter."} />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${grid}, 1fr)`, gap: 10 }}>
          {shown.map((c) => {
            const det = latestDetectionByCamera[c.id];
            const count = detectionCountByCamera[c.id] || 0;
            const isAlert = c.status === "alert";
            const plate = det?.plate && det.plate !== "UNKNOWN" ? det.plate : null;
            const aiStatus = count > 0 ? "AI PROCESSING" : c.status === "offline" ? "NO SIGNAL" : "NO AI FRAMES";
            return (
              <Panel key={c.uuid || c.id} style={isAlert ? { borderColor: C.red } : undefined}>
                <SectionHeader
                  title={c.code || c.id}
                  sub={c.locationDesc || c.name}
                  right={
                    <span style={{ display: "flex", gap: 4 }}>
                      {plate && (
                        <CommandButton small icon={Crosshair}
                          onClick={() => nav(`/workspace?plate=${encodeURIComponent(plate)}`)}>
                          Investigate
                        </CommandButton>
                      )}
                      <CommandButton small onClick={() => nav(`/camera-intelligence/${c.code}`)}>Open</CommandButton>
                    </span>
                  }
                />
                <div style={{ padding: 8, position: "relative" }}>
                  {isAlert && (
                    <span style={{ position: "absolute", top: 12, right: 12, zIndex: 2, background: C.red, color: "#0b0f14", fontSize: 8.5, fontWeight: 800, borderRadius: 3, padding: "1px 5px" }}>
                      ⚠ ACTIVE ALERT
                    </span>
                  )}
                  <CameraPlayer cameraId={c.uuid || c.id} height={grid === 1 ? 420 : grid === 2 ? 240 : 170} />
                </div>
                <div style={{ padding: "4px 10px 8px", display: "flex", gap: 8, fontSize: 9.5, color: C.muted, flexWrap: "wrap", alignItems: "center" }}>
                  <span>FPS {c.fps ?? "—"}</span>
                  <span style={{ color: count > 0 ? C.green : C.amber }}>{aiStatus}</span>
                  <span>{det?.time ? `last det ${det.time}` : "no detections"}</span>
                  {plate && <span style={{ fontFamily: "monospace", color: C.text }}>{plate}</span>}
                  <Badge color={isAlert ? C.red : c.status === "offline" ? C.red : c.status === "active" ? C.green : C.amber}>
                    {isAlert ? "ALERT" : String(c.status || "").toUpperCase()}
                  </Badge>
                </div>
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}
