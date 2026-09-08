import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import {
  AlertTriangle, Bot, Car, Clock, MapPin, Play, Search, ShieldAlert,
} from "lucide-react";
import { C } from "../theme.js";
import GisMap from "../components/gis/GisMap.jsx";
import CameraPlayer from "../components/camera/CameraPlayer.jsx";
import VisualMatchesPanel from "../components/investigation/VisualMatchesPanel.jsx";
import ConfidenceBadge from "../components/ops/ConfidenceBadge.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { fmtDateTime } from "../utils/datetime.js";
import { fetchVehicleProfile } from "../services/investigationApi.js";
import { runInvestigation } from "../services/aiApi.js";
import { normalizePlate } from "../utils/plate.js";

const dot = (col) => L.divIcon({
  className: "",
  html: `<span style="display:block;width:11px;height:11px;border-radius:50%;background:${col};border:2px solid #0b0f14"></span>`,
  iconSize: [11, 11],
});
const GAP_COLOR = { high: C.red, medium: C.amber, low: C.muted };

// Phase 15D — Live Investigation Workspace.
//   LEFT: search + vehicle identity   CENTER: camera evidence + journey map
//   RIGHT: AI investigation summary    BOTTOM: journey timeline
export default function LiveInvestigationWorkspace() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [plate, setPlate] = useState(params.get("plate") || "");
  const [q, setQ] = useState(params.get("plate") || "");
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async (p) => {
    if (!p) return;
    setLoading(true); setErr(""); setReport(null);
    try {
      setProfile(await fetchVehicleProfile(p));
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Vehicle not found");
      setProfile(null);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (plate) load(plate); }, [plate, load]);

  const submit = (e) => {
    e.preventDefault();
    const n = normalizePlate(q);
    setPlate(n); setParams({ plate: n });
  };

  const runAgent = async () => {
    setRunning(true);
    try { setReport(await runInvestigation(`Investigate ${plate}`, plate)); }
    catch (e) { setErr(e?.response?.data?.error?.message || "Investigation failed"); }
    finally { setRunning(false); }
  };

  const sightings = profile?.journey?.transitions || [];
  const cameras = profile?.cameras || [];
  const geo = cameras.filter((c) => c.latitude != null);
  const lastCam = cameras[cameras.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Investigation Workspace</span>
        {profile && (
          <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 14, fontWeight: 700 }}>
            {profile.plate}
          </span>
        )}
        {profile?.is_watchlisted && (
          <span style={{ display: "inline-flex", gap: 4, alignItems: "center", color: C.red, fontSize: 10, fontWeight: 700, border: `1px solid ${C.red}`, borderRadius: 3, padding: "1px 6px" }}>
            <ShieldAlert size={11} /> WATCHLIST · {profile.watchlist_category || "—"}
          </span>
        )}
      </div>

      <form onSubmit={submit} style={{ display: "flex", gap: 8, maxWidth: 460 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Registration plate…"
          style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: "8px 12px", fontFamily: "monospace", fontSize: 13 }} />
        <button type="submit" style={primaryBtn}><Search size={13} /> Open</button>
      </form>

      {err && <ErrorBanner message={err} />}
      {loading && <div style={{ color: C.muted, fontSize: 12 }}>Loading vehicle…</div>}

      {profile && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 320px", gap: 10, alignItems: "start" }}
               className="workspace-grid">
            {/* LEFT — identity */}
            <div style={panel}>
              <div style={panelHead}>Vehicle identity</div>
              <div style={{ padding: 12, display: "grid", gap: 8, fontSize: 12 }}>
                <KV k="Total sightings" v={profile.total_sightings} />
                <KV k="First seen" v={profile.first_seen ? fmtDateTime(profile.first_seen) : "—"} />
                <KV k="Last seen" v={profile.last_seen ? fmtDateTime(profile.last_seen) : "—"} />
                <KV k="Cameras" v={profile.distinct_cameras} />
                <KV k="Type" v={profile.vehicle_types.join(", ") || "—"} />
                <KV k="Colour" v={profile.vehicle_colors.join(", ") || "—"} />
                <KV k="ANPR" v={`${profile.anpr_readable} readable · ${profile.anpr_unknown} unknown`} />
                {Object.keys(profile.anpr_failure_reasons || {}).length > 0 && (
                  <div style={{ color: C.amber, fontSize: 10 }}>
                    {Object.entries(profile.anpr_failure_reasons).map(([r, n]) => `${r}×${n}`).join(" · ")}
                  </div>
                )}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                  {["alerts", "incidents", "cases", "anomalies", "evidence"].map((k) => (
                    <span key={k} style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 3, padding: "2px 6px", fontSize: 9, color: C.muted }}>
                      {k} <b style={{ color: C.text }}>{profile.counts[k] ?? 0}</b>
                    </span>
                  ))}
                  <span style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 3, padding: "2px 6px", fontSize: 9, color: C.muted }}>
                    visual <b style={{ color: C.text }}>{profile.visual_match_count}</b>
                  </span>
                </div>
                <button style={{ ...chip, marginTop: 4 }} onClick={() => nav(`/investigation?plate=${profile.plate}`)}>
                  Full investigation & GIS →
                </button>
                <button style={chip} onClick={() => nav(`/graph?plate=${profile.plate}`)}>
                  Investigation graph →
                </button>
              </div>
            </div>

            {/* CENTER — evidence + map */}
            <div style={{ display: "grid", gap: 10 }}>
              {lastCam && (
                <div style={panel}>
                  <div style={panelHead}>
                    Camera evidence — {lastCam.camera_code} ({lastCam.camera_name})
                  </div>
                  <div style={{ padding: 10 }}>
                    <CameraPlayer cameraId={lastCam.camera_id} height={200} />
                  </div>
                </div>
              )}
              <div style={panel}>
                <div style={panelHead}>Journey map · {geo.length} geolocated camera(s)</div>
                {geo.length ? (
                  <GisMap height={300}
                    center={[geo[0].latitude, geo[0].longitude]} zoom={12}
                    focus={{ lat: geo[0].latitude, lng: geo[0].longitude, zoom: 12 }}>
                    {geo.length > 1 && (
                      <Polyline positions={geo.map((c) => [c.latitude, c.longitude])}
                        pathOptions={{ color: C.accent, weight: 2, dashArray: "4 6" }} />
                    )}
                    {geo.map((c, i) => (
                      <Marker key={c.camera_id} position={[c.latitude, c.longitude]}
                        icon={dot(i === 0 ? C.green : i === geo.length - 1 ? C.red : C.accent)}>
                        <Popup>{c.camera_code} · {c.sightings} sighting(s)<br />{fmtDateTime(c.first_seen)}</Popup>
                      </Marker>
                    ))}
                  </GisMap>
                ) : (
                  <div style={{ padding: 20, color: C.dim, fontSize: 12 }}>No geolocated sightings to plot.</div>
                )}
              </div>
            </div>

            {/* RIGHT — AI summary */}
            <div style={panel}>
              <div style={{ ...panelHead, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}><Bot size={12} /> AI investigation</span>
                <button style={{ ...primaryBtn, padding: "4px 10px", fontSize: 10 }} disabled={running} onClick={runAgent}>
                  <Play size={11} /> {running ? "Running…" : "Run Investigation"}
                </button>
              </div>
              <div style={{ padding: 12 }}>
                {!report ? (
                  <div style={{ color: C.dim, fontSize: 11 }}>
                    Run the multi-step agent for a grounded summary, likely transitions, alerts,
                    anomalies, evidence, investigation gaps, confidence and next useful actions.
                  </div>
                ) : (
                  <div style={{ display: "grid", gap: 10 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontSize: 8, fontWeight: 800, color: C.green, border: `1px solid ${C.green}`, borderRadius: 3, padding: "0 4px" }}>READ-ONLY</span>
                      <ConfidenceBadge level={report.confidence_level} score={report.confidence_score} method={`plan: ${report.plan_source}`} />
                    </div>
                    <div style={{ fontSize: 12, color: C.text, lineHeight: 1.5 }}>{report.summary}</div>
                    {(report.sections || []).map((s, i) => (
                      <div key={i}>
                        <div style={{ fontSize: 8.5, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 }}>{s.title}</div>
                        <div style={{ fontSize: 11, color: C.text }}>{s.body}</div>
                      </div>
                    ))}
                    {(report.gaps || []).length > 0 && (
                      <div>
                        <div style={{ fontSize: 8.5, fontWeight: 700, color: C.amber, textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 3 }}>
                          Investigation gaps
                        </div>
                        {report.gaps.map((g, i) => (
                          <div key={i} style={{ fontSize: 10, color: C.muted, display: "flex", gap: 6, padding: "1px 0" }}>
                            <span style={{ color: GAP_COLOR[g.severity] || C.muted, fontWeight: 700, minWidth: 84, fontSize: 8.5 }}>{g.kind}</span>
                            <span>{g.description}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {(report.related || []).length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {report.related.map((r) => (
                          <Link key={r.id} to={r.href} style={{ ...chip, textDecoration: "none", color: C.accent }}>
                            {r.kind}: {r.label}
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* visual matches */}
          <VisualMatchesPanel plate={profile.plate} />

          {/* BOTTOM — journey timeline */}
          <div style={panel}>
            <div style={panelHead}>Journey timeline · {profile.journey.confirmed_sightings} confirmed · {profile.journey.inferred_transitions} inferred</div>
            <div style={{ padding: 12, overflowX: "auto" }}>
              <div style={{ display: "flex", alignItems: "stretch", gap: 0, minWidth: "min-content" }}>
                {cameras.map((c, i) => (
                  <div key={c.camera_id} style={{ display: "flex", alignItems: "center" }}>
                    <div style={{ minWidth: 120, textAlign: "center" }}>
                      <div style={{ width: 12, height: 12, borderRadius: "50%", margin: "0 auto 4px",
                        background: i === 0 ? C.green : i === cameras.length - 1 ? C.red : C.accent }} />
                      <div style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{c.camera_code}</div>
                      <div style={{ color: C.muted, fontSize: 9, fontFamily: "monospace" }}>{fmtDateTime(c.first_seen)}</div>
                      <div style={{ color: C.dim, fontSize: 9 }}>{c.location_desc || ""}</div>
                    </div>
                    {i < cameras.length - 1 && (() => {
                      const t = sightings[i];
                      return (
                        <div style={{ minWidth: 110, textAlign: "center", fontSize: 9, color: C.muted, padding: "0 4px" }}>
                          <div style={{ borderTop: `1px dashed ${C.border}`, margin: "18px 0 4px" }} />
                          {t ? (
                            <>
                              <span style={{ color: C.amber, fontWeight: 700 }}>INFERRED</span><br />
                              {Math.round(t.time_diff_seconds / 60)} min
                              {t.distance_meters != null ? ` · ${(t.distance_meters / 1000).toFixed(1)} km` : ""}
                              {t.estimated_speed_kmh != null ? ` · ~${t.estimated_speed_kmh} km/h` : ""}
                              <br /><span style={{ color: t.transition_classification === "IMPOSSIBLE" ? C.red : C.dim }}>
                                {t.transition_classification || ""}
                              </span>
                            </>
                          ) : "→"}
                        </div>
                      );
                    })()}
                  </div>
                ))}
              </div>
              <div style={{ color: C.dim, fontSize: 9, marginTop: 8 }}>
                <b style={{ color: C.green }}>●</b> first sighting &nbsp;
                <b style={{ color: C.red }}>●</b> last sighting &nbsp;·&nbsp;
                Camera sightings are CONFIRMED; transitions between them are INFERRED (not observed).
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <span style={{ color: C.muted }}>{k}</span>
      <span style={{ color: C.text, textAlign: "right", fontFamily: "monospace" }}>{String(v)}</span>
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const panelHead = { padding: "9px 12px", borderBottom: `1px solid ${C.border}`, fontWeight: 600, fontSize: 11.5, color: C.text };
const primaryBtn = { display: "inline-flex", alignItems: "center", gap: 6, background: C.accent, color: "#0b0f14", border: "none", borderRadius: 6, padding: "8px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" };
const chip = { display: "inline-flex", alignItems: "center", gap: 5, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 9px", fontSize: 10.5, cursor: "pointer", justifyContent: "center" };
