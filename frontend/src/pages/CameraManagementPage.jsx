import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Video, RefreshCw } from "lucide-react";
import { C, CAMERA_STATUS_COLOR } from "../theme.js";
import CameraModal from "../components/CameraModal.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { fmtDateTime, fmtRelative } from "../utils/datetime.js";

const SRC = ["ALL", "REAL", "MOCK"];
const STA = ["ALL", "active", "degraded", "offline"];

// Lightweight Camera Management console (Phase 13 §4). Table view over the
// existing /api/v1/cameras data — search / filter / status / REAL·MOCK /
// last seen / location. Row → the existing camera modal (health history,
// GIS, recent events). No device-management infra; no credential handling.
export default function CameraManagementPage() {
  const { cameras = [], loading, backendLive, retrying, reload } = useOutletContext();
  const [selected, setSelected] = useState(null);
  const [q, setQ] = useState("");
  const [src, setSrc] = useState("ALL");
  const [sta, setSta] = useState("ALL");

  const isMock = (c) => (c.isMockBackend != null ? c.isMockBackend : c.isMock);

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return cameras.filter((c) => {
      if (src === "REAL" && isMock(c)) return false;
      if (src === "MOCK" && !isMock(c)) return false;
      if (sta !== "ALL" && c.status !== sta) return false;
      if (term && !`${c.id} ${c.code || ""} ${c.name} ${c.locationDesc || ""}`.toLowerCase().includes(term))
        return false;
      return true;
    });
  }, [cameras, q, src, sta]);

  const counts = useMemo(() => ({
    total: cameras.length,
    online: cameras.filter((c) => c.status === "active" || c.status === "alert").length,
    offline: cameras.filter((c) => c.status === "offline").length,
    real: cameras.filter((c) => !isMock(c)).length,
    mock: cameras.filter((c) => isMock(c)).length,
  }), [cameras]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Video size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Camera Management</span>
        <span style={{ color: C.muted, fontSize: 12 }}>
          · {counts.total} total · {counts.online} online · {counts.offline} offline ·{" "}
          <span style={{ color: C.green }}>{counts.real} REAL</span> ·{" "}
          <span style={{ color: C.violet }}>{counts.mock} MOCK</span>
        </span>
        <button onClick={reload} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Registry, effective health and last-seen for every camera. Click a row for health history, GIS and recent events.
        Government feed credentials are never shown or editable here.
      </div>

      {!backendLive && (
        <ErrorBanner message="Backend unreachable — showing last-known camera data." onRetry={reload} retrying={retrying} />
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search id / name / location…"
               style={{ ...input, flex: "1 1 200px" }} />
        <label style={lbl}>Source<select value={src} onChange={(e) => setSrc(e.target.value)} style={input}>
          {SRC.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label style={lbl}>Status<select value={sta} onChange={(e) => setSta(e.target.value)} style={input}>
          {STA.map((s) => <option key={s} value={s}>{s === "ALL" ? "All" : s}</option>)}</select></label>
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={8} height={38} /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Video} title="No cameras match" hint="Adjust the filters." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase" }}>
                  <th style={th}>Camera</th><th style={th}>Source</th><th style={th}>Status</th>
                  <th style={th}>Location</th><th style={th}>Coords</th><th style={th}>Last heartbeat</th>
                  <th style={th}>Last detection</th><th style={th}>FPS</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.uuid || c.id} onClick={() => setSelected(c)}
                      style={{ borderTop: `1px solid ${C.border}`, cursor: "pointer" }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = C.panel)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <td style={td}>
                      <div style={{ fontFamily: "monospace", color: C.accent }}>{c.code || c.id}</div>
                      <div style={{ color: C.text }}>{c.name}</div>
                    </td>
                    <td style={td}>
                      <span style={{ color: isMock(c) ? C.violet : C.green, border: `1px solid ${isMock(c) ? C.violet : C.green}55`, borderRadius: 3, padding: "1px 6px", fontSize: 9, fontWeight: 700 }}>
                        {isMock(c) ? "MOCK" : "REAL"}
                      </span>
                    </td>
                    <td style={td}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: CAMERA_STATUS_COLOR[c.status] || C.muted, fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: CAMERA_STATUS_COLOR[c.status] || C.muted }} />
                        {c.status === "active" ? "online" : c.status}
                      </span>
                    </td>
                    <td style={{ ...td, color: C.muted, maxWidth: 200 }}>{c.locationDesc || "—"}</td>
                    <td style={{ ...td, color: C.dim, fontFamily: "monospace", fontSize: 10 }}>
                      {c.lat != null ? `${c.lat.toFixed(4)}, ${c.lng.toFixed(4)}` : "—"}
                    </td>
                    <td style={{ ...td, color: C.muted }} title={fmtDateTime(c.healthUpdatedAt)}>
                      {c.healthUpdatedAt ? fmtRelative(c.healthUpdatedAt) : "never reported"}
                    </td>
                    <td style={{ ...td, color: C.muted }} title={fmtDateTime(c.lastDetectionAt)}>
                      {c.lastDetectionAt ? fmtRelative(c.lastDetectionAt) : "—"}
                    </td>
                    <td style={{ ...td, color: C.muted, fontFamily: "monospace" }}>
                      {typeof c.fps === "number" ? c.fps.toFixed(1) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <CameraModal cam={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const th = { padding: "9px 12px" };
const td = { padding: "9px 12px", verticalAlign: "top" };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11 };
const iconBtn = { ...input, cursor: "pointer", display: "inline-flex", alignItems: "center" };
const lbl = { fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 5 };
