import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import {
  Bot, ChevronLeft, ChevronRight, ExternalLink, FileBarChart, Network,
  Pause, Play, Search, ShieldAlert, MapPinned,
} from "lucide-react";
import { C } from "../theme.js";
import GisMap from "../components/gis/GisMap.jsx";
import CameraPlayer from "../components/camera/CameraPlayer.jsx";
import VisualMatchesPanel from "../components/investigation/VisualMatchesPanel.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import {
  Badge, ConfidenceBadge, SourceBadge, VerdictBadge, Panel, SectionHeader,
  CommandButton, EntityLink, TimelineDot,
} from "../components/ui/primitives.jsx";
import { fmtDateTime } from "../utils/datetime.js";
import { fetchVehicleProfile, searchVehicle, evidenceUrl } from "../services/investigationApi.js";
import { useMediaTicket } from "../services/mediaTicket.js";
import { runInvestigation } from "../services/aiApi.js";
import { normalizePlate } from "../utils/plate.js";

const dot = (col, big) => L.divIcon({
  className: "",
  html: `<span style="display:block;width:${big ? 17 : 11}px;height:${big ? 17 : 11}px;border-radius:50%;background:${col};border:2px solid #0b0f14;box-shadow:${big ? `0 0 10px ${col}` : "none"}"></span>`,
  iconSize: [big ? 17 : 11, big ? 17 : 11],
});
const GAP_COLOR = { high: C.red, medium: C.amber, low: C.muted };
const CLS_COLOR = { IMPOSSIBLE: C.red, FAST: C.amber, SLOW: C.amber, PLAUSIBLE: C.green };

// Phase 16C–16E — SENTINEL Investigation Workspace.
// One screen: VEHICLE IDENTITY · EVIDENCE + JOURNEY MAP · INVESTIGATION
// TIMELINE · AI INVESTIGATION. Map ⇄ timeline ⇄ evidence stay synchronised
// through a single `selIdx`. CONFIRMED sightings and INFERRED transitions
// are always visually distinct.
export default function LiveInvestigationWorkspace() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [plate, setPlate] = useState(params.get("plate") || "");
  const [q, setQ] = useState(params.get("plate") || "");
  const [profile, setProfile] = useState(null);
  const [sightings, setSightings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState(null);
  const [running, setRunning] = useState(false);
  const [selIdx, setSelIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  const load = useCallback(async (p) => {
    if (!p) return;
    setLoading(true); setErr(""); setReport(null); setSelIdx(0); setPlaying(false);
    try {
      const [prof, search] = await Promise.all([
        fetchVehicleProfile(p),
        searchVehicle(p).catch(() => ({ data: { sightings: [] } })),
      ]);
      setProfile(prof);
      setSightings(search?.data?.sightings || []);
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Vehicle not found");
      setProfile(null); setSightings([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (plate) load(plate); }, [plate, load]);

  // sync selected sighting index -> URL (investigation session persistence)
  useEffect(() => {
    if (!plate) return;
    const next = new URLSearchParams(params);
    next.set("plate", plate);
    if (sightings[selIdx]) next.set("evt", String(selIdx)); else next.delete("evt");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selIdx, plate, sightings.length]);

  // restore selected index from URL on first load
  useEffect(() => {
    const evt = Number(params.get("evt"));
    if (Number.isFinite(evt) && evt >= 0 && evt < sightings.length) setSelIdx(evt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sightings.length]);

  // timeline scrubber
  useEffect(() => {
    if (!playing || !sightings.length) return;
    const id = setInterval(() => {
      setSelIdx((i) => {
        if (i >= sightings.length - 1) { setPlaying(false); return i; }
        return i + 1;
      });
    }, 1600);
    return () => clearInterval(id);
  }, [playing, sightings.length]);

  // keyboard: ← / → step evidence, space play/pause (only when not typing)
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || e.target?.isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === "j" || e.key === "J") { e.preventDefault(); step(1); }
      else if (e.key === "ArrowLeft" || e.key === "k" || e.key === "K") { e.preventDefault(); step(-1); }
      else if (e.key === " ") { e.preventDefault(); setPlaying((p) => !p); }
      else if (e.key === "e" || e.key === "E") {
        const s = sightings[selIdx];
        if (s) window.open(evidenceUrl(s.eventId), "_blank", "noopener");
      }
      else if (e.key === "g" || e.key === "G") {
        if (profile?.plate) nav(`/graph?plate=${profile.plate}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sightings.length, selIdx, profile]);

  const step = (d) => setSelIdx((i) => Math.max(0, Math.min(sightings.length - 1, i + d)));

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

  const transitions = profile?.journey?.transitions || [];
  const geoSightings = useMemo(() => sightings.filter((s) => s.hasLocation), [sightings]);
  const sel = sightings[selIdx] || null;
  const avgConf = useMemo(() => {
    const xs = sightings.map((s) => s.ocrConfidence).filter((x) => Number.isFinite(x));
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  }, [sightings]);
  const highConfidence = avgConf != null && avgConf >= 0.85;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* ── header ─────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ color: C.muted, fontSize: 10, fontWeight: 800, letterSpacing: 1.5 }}>VEHICLE</span>
        <span style={{ fontFamily: "'Space Mono', monospace", color: C.accent, fontSize: 18, fontWeight: 700 }}>
          {profile?.plate || plate || "—"}
        </span>
        {profile && (
          <>
            {profile.is_watchlisted && (
              <Badge color={C.red} filled>
                <ShieldAlert size={10} /> WATCHLIST · {profile.watchlist_category || "—"}
              </Badge>
            )}
            {highConfidence && <Badge color={C.green}>HIGH CONFIDENCE · {Math.round(avgConf * 100)}%</Badge>}
            <Badge color={C.accent}>{profile.total_sightings} SIGHTINGS</Badge>
            <Badge color={C.accent}>{profile.distinct_cameras} CAMERAS</Badge>
            <Badge color={(profile.counts?.alerts || 0) ? C.amber : C.muted}>{profile.counts?.alerts || 0} ALERTS</Badge>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
              <CommandButton small icon={Bot} onClick={() => nav(`/copilot?q=${encodeURIComponent(`Investigate ${profile.plate}`)}`)}>
                Ask SENTINEL
              </CommandButton>
              <CommandButton small icon={Network} to={`/graph?plate=${profile.plate}`}>Open Graph</CommandButton>
              <CommandButton small icon={MapPinned} to={`/investigation?plate=${profile.plate}`}>Full GIS</CommandButton>
              <CommandButton small icon={FileBarChart} to={`/reports?plate=${profile.plate}`}>Generate Report</CommandButton>
            </div>
          </>
        )}
      </div>

      <form onSubmit={submit} style={{ display: "flex", gap: 8, maxWidth: 460 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Registration plate…"
          style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: "8px 12px", fontFamily: "monospace", fontSize: 13 }} />
        <CommandButton primary icon={Search}>Open</CommandButton>
      </form>

      {err && <ErrorBanner message={err} />}
      {loading && <div style={{ color: C.muted, fontSize: 12 }}>Loading investigation…</div>}

      {profile && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 340px", gap: 10, alignItems: "start" }}
               className="workspace-grid">
            {/* ── LEFT — vehicle identity ──────────────────────────────── */}
            <Panel>
              <SectionHeader title="Vehicle identity" />
              <div style={{ padding: 12, display: "grid", gap: 8, fontSize: 12 }}>
                <KV k="Total sightings" v={profile.total_sightings} />
                <KV k="First seen" v={profile.first_seen ? fmtDateTime(profile.first_seen) : "—"} />
                <KV k="Last seen" v={profile.last_seen ? fmtDateTime(profile.last_seen) : "—"} />
                <KV k="Distinct cameras" v={profile.distinct_cameras} />
                <KV k="Type" v={profile.vehicle_types.join(", ") || "—"} />
                <KV k="Colour" v={profile.vehicle_colors.join(", ") || "—"} />
                <KV k="ANPR" v={`${profile.anpr_readable} readable · ${profile.anpr_unknown} unknown`} />
                {Object.keys(profile.anpr_failure_reasons || {}).length > 0 && (
                  <div style={{ color: C.amber, fontSize: 10 }}>
                    {Object.entries(profile.anpr_failure_reasons).map(([r, n]) => `${r}×${n}`).join(" · ")}
                  </div>
                )}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 }}>
                  {["alerts", "incidents", "cases", "anomalies", "evidence"].map((k) => (
                    <span key={k} style={countChip}>
                      {k} <b style={{ color: C.text }}>{profile.counts[k] ?? 0}</b>
                    </span>
                  ))}
                  <span style={countChip}>visual <b style={{ color: C.text }}>{profile.visual_match_count}</b></span>
                </div>

                {(profile.related || []).length > 0 && (
                  <div style={{ display: "grid", gap: 5, marginTop: 4 }}>
                    <div style={miniHead}>Related entities</div>
                    {profile.related.map((r) => (
                      <EntityLink key={r.id} to={r.href} kind={r.kind} label={r.label} sub={r.status} />
                    ))}
                  </div>
                )}
              </div>
            </Panel>

            {/* ── CENTER — evidence + map ──────────────────────────────── */}
            <div style={{ display: "grid", gap: 10 }}>
              {/* evidence carousel */}
              <Panel>
                <SectionHeader
                  title="Evidence"
                  sub={sightings.length ? `sighting ${selIdx + 1} of ${sightings.length}` : "no sightings"}
                  right={
                    <span style={{ display: "flex", gap: 4 }}>
                      <button style={navBtn} onClick={() => step(-1)} disabled={selIdx <= 0} title="Previous (←)">
                        <ChevronLeft size={13} />
                      </button>
                      <button style={navBtn} onClick={() => step(1)} disabled={selIdx >= sightings.length - 1} title="Next (→)">
                        <ChevronRight size={13} />
                      </button>
                    </span>
                  }
                />
                {sel ? (
                  <div style={{ padding: 10, display: "grid", gap: 8 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <EvidenceImg eventId={sel.eventId} label="Scene / vehicle crop" />
                      <EvidenceImg eventId={sel.eventId} label="Plate crop" plate />
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                      <VerdictBadge verdict={sel.kind || "CONFIRMED"} />
                      <SourceBadge source={sel.feedSource || (sel.isMock ? "MOCK" : "REAL")} />
                      <Badge color={sel.anprStatus === "OK" ? C.green : C.amber}>
                        ANPR {sel.anprStatus || "OK"}
                      </Badge>
                      {Number.isFinite(sel.ocrConfidence) && (
                        <Badge color={sel.ocrConfidence >= 0.85 ? C.green : sel.ocrConfidence >= 0.6 ? C.amber : C.red}>
                          OCR {Math.round(sel.ocrConfidence * 100)}%
                        </Badge>
                      )}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3px 10px", fontSize: 11 }}>
                      <KV k="Camera" v={`${sel.cameraCode || "?"} · ${sel.cameraName || ""}`} />
                      <KV k="Time" v={fmtDateTime(sel.timestamp)} />
                      <KV k="Location" v={sel.locationDesc || (sel.hasLocation ? "geolocated" : "location unavailable")} />
                      <KV k="Type / colour" v={`${sel.vehicleType || "—"} / ${sel.vehicleColor || "—"}`} />
                      {sel.anprFailureReason && <KV k="ANPR note" v={sel.anprFailureReason} />}
                      {sel.trackId != null && <KV k="Track" v={sel.trackId} />}
                    </div>
                    <a href={evidenceUrl(sel.eventId)} target="_blank" rel="noreferrer"
                       style={{ ...miniHead, color: C.accent, display: "inline-flex", gap: 4, alignItems: "center", textDecoration: "none" }}>
                      <ExternalLink size={11} /> Open full evidence
                    </a>
                    <div style={{ color: C.dim, fontSize: 9 }}>
                      This sighting is a CONFIRMED observation. The image shown is the stored evidence crop
                      for this detection — never a live feed.
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: 20, color: C.dim, fontSize: 12 }}>No sighting evidence to show.</div>
                )}
              </Panel>

              {/* live camera for the selected sighting */}
              {sel?.cameraId && (
                <Panel>
                  <SectionHeader title={`Camera feed — ${sel.cameraCode || ""}`} sub={sel.cameraName || ""} />
                  <div style={{ padding: 10 }}>
                    <CameraPlayer cameraId={sel.cameraId} height={190} />
                  </div>
                </Panel>
              )}

              {/* journey map */}
              <Panel>
                <SectionHeader title="Journey map" sub={`${geoSightings.length} geolocated sighting(s) · route is INFERRED`} />
                {geoSightings.length ? (
                  <GisMap height={300}
                    center={[geoSightings[0].lat, geoSightings[0].lng]} zoom={12}
                    focus={sel?.hasLocation ? { lat: sel.lat, lng: sel.lng, zoom: 13 } : null}>
                    {geoSightings.length > 1 && (
                      <Polyline positions={geoSightings.map((s) => [s.lat, s.lng])}
                        pathOptions={{ color: C.accent, weight: 2, dashArray: "4 6" }} />
                    )}
                    {geoSightings.map((s) => {
                      const idx = sightings.indexOf(s);
                      const isSel = idx === selIdx;
                      const first = idx === 0, last = idx === sightings.length - 1;
                      return (
                        <Marker key={s.eventId} position={[s.lat, s.lng]}
                          icon={dot(isSel ? C.text : first ? C.green : last ? C.red : C.accent, isSel)}
                          eventHandlers={{ click: () => setSelIdx(idx) }}>
                          <Popup>
                            <b>{s.cameraCode}</b> · sighting {idx + 1}<br />
                            {fmtDateTime(s.timestamp)}
                          </Popup>
                        </Marker>
                      );
                    })}
                  </GisMap>
                ) : (
                  <div style={{ padding: 20, color: C.dim, fontSize: 12 }}>No geolocated sightings to plot.</div>
                )}
              </Panel>
            </div>

            {/* ── RIGHT — AI investigation ─────────────────────────────── */}
            <Panel>
              <SectionHeader
                icon={Bot} title="AI investigation"
                right={
                  <CommandButton small primary icon={Play} disabled={running} onClick={runAgent}>
                    {running ? "Running…" : "Run"}
                  </CommandButton>
                }
              />
              <div style={{ padding: 12 }}>
                {!report ? (
                  <div style={{ color: C.dim, fontSize: 11 }}>
                    Run the multi-step agent for a grounded summary: likely transitions, alerts,
                    anomalies, evidence, investigation gaps, confidence and next useful actions.
                    The agent is <b style={{ color: C.green }}>READ-ONLY</b> — it never modifies case state.
                  </div>
                ) : (
                  <div style={{ display: "grid", gap: 10 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <Badge color={C.green}>READ-ONLY</Badge>
                      <ConfidenceBadge level={report.confidence_level} score={report.confidence_score}
                        method={`plan: ${report.plan_source}`} />
                    </div>
                    <div style={{ fontSize: 12, color: C.text, lineHeight: 1.5 }}>{report.summary}</div>
                    {(report.sections || []).map((s, i) => (
                      <div key={i}>
                        <div style={miniHead}>{s.title}</div>
                        <div style={{ fontSize: 11, color: C.text }}>{s.body}</div>
                      </div>
                    ))}
                    {(report.gaps || []).length > 0 && (
                      <div>
                        <div style={{ ...miniHead, color: C.amber }}>Investigation gaps</div>
                        {report.gaps.map((g, i) => (
                          <div key={i} style={{ fontSize: 10, color: C.muted, display: "flex", gap: 6, padding: "1px 0" }}>
                            <span style={{ color: GAP_COLOR[g.severity] || C.muted, fontWeight: 700, minWidth: 84, fontSize: 8.5 }}>
                              {g.kind}
                            </span>
                            <span>{g.description}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {(report.related || []).length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {report.related.map((r) => (
                          <Link key={r.id} to={r.href} style={relChip}>{r.kind}: {r.label}</Link>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Panel>
          </div>

          {/* visual matches (visual similarity ≠ identity) */}
          <VisualMatchesPanel plate={profile.plate} />

          {/* ── BOTTOM — investigation timeline ────────────────────────── */}
          <Panel>
            <SectionHeader
              title="Investigation timeline"
              sub={`${profile.journey.confirmed_sightings} confirmed · ${profile.journey.inferred_transitions} inferred transition(s)`}
              right={
                <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <button style={navBtn} onClick={() => step(-1)} disabled={selIdx <= 0} title="Prev (←)"><ChevronLeft size={13} /></button>
                  <button style={navBtn} onClick={() => setPlaying((p) => !p)} title="Play / pause (space)">
                    {playing ? <Pause size={13} /> : <Play size={13} />}
                  </button>
                  <button style={navBtn} onClick={() => step(1)} disabled={selIdx >= sightings.length - 1} title="Next (→)"><ChevronRight size={13} /></button>
                </span>
              }
            />
            <div style={{ padding: 12, overflowX: "auto" }}>
              <div style={{ display: "flex", alignItems: "stretch", minWidth: "min-content" }}>
                {sightings.map((s, i) => {
                  const first = i === 0, last = i === sightings.length - 1;
                  const isSel = i === selIdx;
                  return (
                    <div key={s.eventId} style={{ display: "flex", alignItems: "center" }}>
                      <button onClick={() => setSelIdx(i)} style={{
                        minWidth: 128, textAlign: "center", background: isSel ? C.panel : "transparent",
                        border: `1px solid ${isSel ? C.accent : "transparent"}`, borderRadius: 6,
                        padding: "6px 4px", cursor: "pointer", color: C.text,
                      }}>
                        <div style={{ display: "flex", justifyContent: "center", marginBottom: 4 }}>
                          <TimelineDot active={isSel} color={first ? C.green : last ? C.red : C.accent} />
                        </div>
                        <div style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{s.cameraCode}</div>
                        <div style={{ color: C.muted, fontSize: 9, fontFamily: "monospace" }}>{fmtDateTime(s.timestamp)}</div>
                        <div style={{ color: C.dim, fontSize: 9 }}>{s.locationDesc || ""}</div>
                        <div style={{ marginTop: 3 }}>
                          <span style={{ fontSize: 7.5, fontWeight: 800, color: C.green, border: `1px solid ${C.green}`, borderRadius: 2, padding: "0 3px" }}>
                            CONFIRMED
                          </span>
                        </div>
                      </button>
                      {i < sightings.length - 1 && (() => {
                        const t = transitions[i];
                        return (
                          <div style={{ minWidth: 128, textAlign: "center", fontSize: 9, color: C.muted, padding: "0 6px" }}>
                            <div style={{ borderTop: `1px dashed ${C.border}`, margin: "20px 0 5px" }} />
                            {t ? (
                              <>
                                <span style={{ color: C.amber, fontWeight: 800, fontSize: 7.5, border: `1px solid ${C.amber}`, borderRadius: 2, padding: "0 3px" }}>
                                  INFERRED
                                </span>
                                <div style={{ marginTop: 3 }}>
                                  {Math.round(t.time_diff_seconds / 60)} min
                                  {t.distance_meters != null ? ` · ${(t.distance_meters / 1000).toFixed(1)} km` : ""}
                                </div>
                                {t.estimated_speed_kmh != null && <div>~{t.estimated_speed_kmh} km/h</div>}
                                {t.expected_travel_band && (
                                  <div style={{ color: C.dim, fontSize: 8 }}>{t.expected_travel_band}</div>
                                )}
                                {t.transition_classification && (
                                  <div style={{ color: CLS_COLOR[t.transition_classification] || C.dim, fontWeight: 700 }}>
                                    {t.transition_classification}
                                  </div>
                                )}
                              </>
                            ) : <span>→</span>}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })}
              </div>
              <div style={{ color: C.dim, fontSize: 9, marginTop: 8 }}>
                <b style={{ color: C.green }}>●</b> first sighting &nbsp;
                <b style={{ color: C.red }}>●</b> last sighting &nbsp;·&nbsp;
                Camera sightings are <b style={{ color: C.green }}>CONFIRMED</b>; movement between them is
                <b style={{ color: C.amber }}> INFERRED</b> (not observed). Speed / travel-band figures are estimates.
              </div>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}

// evidence image — the backend serves an honestly-labelled placeholder SVG
// (HTTP 200) when no crop reached this host, so a plain <img> is enough;
// keep a text fallback for a hard network failure.
function EvidenceImg({ eventId, label, plate }) {
  const [failed, setFailed] = useState(false);
  const ticket = useMediaTicket(); // "" until a real credential exists -- don't render <img> before then
  return (
    <div style={{ display: "grid", gap: 3 }}>
      <div style={{ fontSize: 8.5, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
      {failed || !ticket ? (
        <div style={{ height: plate ? 70 : 130, display: "flex", alignItems: "center", justifyContent: "center",
          background: C.bg, border: `1px dashed ${C.border}`, color: C.dim, fontSize: 10 }}>
          {failed ? "evidence unavailable" : "loading…"}
        </div>
      ) : (
        <img src={evidenceUrl(eventId)} alt={label} onError={() => setFailed(true)}
          style={{ width: "100%", height: plate ? 70 : 130, objectFit: "cover",
            background: C.bg, border: `1px solid ${C.border}`, borderRadius: 4 }} />
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

const miniHead = { fontSize: 8.5, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 };
const countChip = { background: C.bg, border: `1px solid ${C.border}`, borderRadius: 3, padding: "2px 6px", fontSize: 9, color: C.muted };
const navBtn = { display: "inline-flex", alignItems: "center", justifyContent: "center", width: 24, height: 22, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, cursor: "pointer" };
const relChip = { display: "inline-flex", alignItems: "center", gap: 5, background: C.panel, border: `1px solid ${C.border}`, color: C.accent, borderRadius: 4, padding: "5px 9px", fontSize: 10.5, textDecoration: "none" };
