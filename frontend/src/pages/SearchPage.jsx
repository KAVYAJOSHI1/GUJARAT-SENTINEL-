import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bookmark, RotateCcw, Search, Sparkles, Trash2 } from "lucide-react";
import { C } from "../theme.js";
import { canManageOps } from "../services/api.js";
import { aiSearch } from "../services/aiApi.js";
import { useToast } from "../context/ToastContext.jsx";
import {
  createSavedSearch, deleteSavedSearch, listSavedSearches, searchVehicles,
} from "../services/opsApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { Pager } from "./IncidentsPage.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const EMPTY = {
  plate: "", plate_contains: "", vehicle_type: "", camera_code: "", location_contains: "",
  date_from: "", date_to: "", time_from: "", time_to: "", min_confidence: "",
  watchlist_only: false, has_alert: "", has_incident: "", has_case: "", source: "",
  sort: "latest",
};
const PAGE = 25;

// Unified Advanced Search (Phase 11 FEATURE 1). Backend-filtered + paginated;
// every result links into the connected pages.
export default function SearchPage() {
  const navigate = useNavigate();
  const { push } = useToast();
  const [f, setF] = useState(EMPTY);
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [saved, setSaved] = useState([]);
  const [ran, setRan] = useState(false);
  const [nl, setNl] = useState("");
  const [nlBusy, setNlBusy] = useState(false);
  const [nlParsed, setNlParsed] = useState(null);

  const runNL = async (e) => {
    e?.preventDefault();
    if (!nl.trim()) return;
    setNlBusy(true);
    try {
      const r = await aiSearch(nl.trim(), { limit: PAGE, offset: 0 });
      const flt = r.filters || {};
      setNlParsed(flt);
      // hydrate the structured form so the officer sees + can tweak it
      setF({
        ...EMPTY,
        plate: flt.plate || "",
        vehicle_type: flt.vehicle_type || "",
        vehicle_color: flt.vehicle_color || "",
        camera_code: flt.camera_code || "",
        date_from: flt.date_from ? String(flt.date_from).slice(0, 16) : "",
        date_to: flt.date_to ? String(flt.date_to).slice(0, 16) : "",
        time_from: flt.time_from || "",
        time_to: flt.time_to || "",
        watchlist_only: !!flt.watchlist_only,
        sort: "latest",
      });
      setRes(r.search);
      setRan(true);
      setOffset(0);
      if (r.limitations?.length) push({ title: "AI search note", msg: r.limitations[0], severity: "medium" });
    } catch (err) {
      push({ title: "AI search failed", msg: err?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setNlBusy(false);
    }
  };

  const loadSaved = useCallback(() => {
    listSavedSearches().then((d) => setSaved(d.items || [])).catch(() => {});
  }, []);
  useEffect(() => { loadSaved(); }, [loadSaved]);

  const params = useMemo(() => {
    const p = { sort: f.sort, limit: PAGE, offset };
    for (const [k, v] of Object.entries(f)) {
      if (k === "sort") continue;
      if (v === "" || v === false) continue;
      if (["has_alert", "has_incident", "has_case"].includes(k)) p[k] = v === "yes";
      else if (k === "min_confidence") p[k] = Number(v);
      else p[k] = v;
    }
    return p;
  }, [f, offset]);

  const run = useCallback(async () => {
    setLoading(true);
    setError(false);
    setRan(true);
    try {
      setRes(await searchVehicles(params));
    } catch {
      setError(true);
      setRes(null);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    if (ran) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, f.sort]);

  const submit = (e) => {
    e?.preventDefault();
    setOffset(0);
    run();
  };

  const saveCurrent = async () => {
    const title = window.prompt("Name this investigation:", "Vehicle sweep");
    if (!title) return;
    try {
      await createSavedSearch({ title, params: { ...f } });
      push({ title: "Investigation saved", severity: "medium" });
      loadSaved();
    } catch {
      push({ title: "Could not save", severity: "high" });
    }
  };

  const openSaved = (s) => {
    setF({ ...EMPTY, ...(s.params || {}) });
    setOffset(0);
    setRan(true);
    setTimeout(run, 0);
  };

  const items = res?.items || [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Search size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Advanced Investigation Search</span>
        {res?.took_ms != null && (
          <span style={{ color: C.dim, fontSize: 10, fontFamily: "monospace" }}>{res.took_ms} ms</span>
        )}
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Search real vehicle events across cameras, dates, watchlist status and alert / incident / case links.
      </div>

      {error && <ErrorBanner message="Search failed." onRetry={run} />}

      {/* Phase 12 — natural-language search: translates into the structured
          filters below and runs the same engine. */}
      <form onSubmit={runNL} style={{ ...panel, padding: 10, marginBottom: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Sparkles size={13} color={C.accent} />
        <input
          value={nl}
          onChange={(e) => setNl(e.target.value)}
          placeholder='Ask in plain English — e.g. "white cars near CAM-04 after 9 PM"'
          style={{ flex: "1 1 260px", background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 5, padding: "7px 10px", fontSize: 12 }}
        />
        <button type="submit" disabled={nlBusy || !nl.trim()} style={primaryBtn}>
          {nlBusy ? "Interpreting…" : "AI search"}
        </button>
        {nlParsed && (
          <span style={{ fontSize: 10, color: C.muted }}>
            interpreted → {Object.entries(nlParsed).filter(([, v]) => v !== undefined && v !== false)
              .map(([k, v]) => `${k}:${v}`).join("  ") || "no filters"}
          </span>
        )}
      </form>

      <form onSubmit={submit} style={{ ...panel, padding: 12, marginBottom: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8 }}>
          <In label="Plate (exact)" v={f.plate} on={(v) => setF({ ...f, plate: v })} mono />
          <In label="Plate contains" v={f.plate_contains} on={(v) => setF({ ...f, plate_contains: v })} mono />
          <In label="Vehicle type" v={f.vehicle_type} on={(v) => setF({ ...f, vehicle_type: v })} />
          <In label="Camera code" v={f.camera_code} on={(v) => setF({ ...f, camera_code: v })} mono />
          <In label="Location / dept" v={f.location_contains} on={(v) => setF({ ...f, location_contains: v })} />
          <In label="Date from" type="datetime-local" v={f.date_from} on={(v) => setF({ ...f, date_from: v })} />
          <In label="Date to" type="datetime-local" v={f.date_to} on={(v) => setF({ ...f, date_to: v })} />
          <In label="Time from" type="time" v={f.time_from} on={(v) => setF({ ...f, time_from: v })} />
          <In label="Time to" type="time" v={f.time_to} on={(v) => setF({ ...f, time_to: v })} />
          <In label="Min confidence (0-1)" type="number" v={f.min_confidence} on={(v) => setF({ ...f, min_confidence: v })} />
          <Sel label="Source" v={f.source} on={(v) => setF({ ...f, source: v })} opts={["", "REAL", "MOCK"]} />
          <Sel label="Has alert" v={f.has_alert} on={(v) => setF({ ...f, has_alert: v })} opts={["", "yes", "no"]} />
          <Sel label="Has incident" v={f.has_incident} on={(v) => setF({ ...f, has_incident: v })} opts={["", "yes", "no"]} />
          <Sel label="Has case" v={f.has_case} on={(v) => setF({ ...f, has_case: v })} opts={["", "yes", "no"]} />
          <Sel label="Sort" v={f.sort} on={(v) => setF({ ...f, sort: v })}
               opts={["latest", "earliest", "confidence", "camera"]} />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 5 }}>
            <input type="checkbox" checked={f.watchlist_only}
                   onChange={(e) => setF({ ...f, watchlist_only: e.target.checked })} />
            Watchlist matches only
          </label>
          <button type="submit" style={primaryBtn}><Search size={12} /> Search</button>
          <button type="button" style={btn} onClick={() => { setF(EMPTY); setRes(null); setRan(false); }}>
            <RotateCcw size={12} /> Clear
          </button>
          <button type="button" style={btn} onClick={saveCurrent}><Bookmark size={12} /> Save investigation</button>
        </div>
      </form>

      {saved.length > 0 && (
        <div style={{ ...panel, padding: "8px 12px", marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 6 }}>
            Saved investigations
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {saved.map((s) => (
              <span key={s.id} style={{
                display: "inline-flex", alignItems: "center", gap: 6, background: C.panel,
                border: `1px solid ${C.border}`, borderRadius: 4, padding: "3px 8px", fontSize: 11,
              }}>
                <button onClick={() => openSaved(s)} style={{ ...linkBtn, color: C.text }} title={s.description || ""}>
                  {s.title}
                </button>
                <button onClick={() => deleteSavedSearch(s.id).then(loadSaved)} style={{ ...linkBtn, color: C.red }}>
                  <Trash2 size={10} />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={6} height={40} /></div>
        ) : !ran ? (
          <EmptyState icon={Search} title="Run a search" hint="Set one or more filters above." />
        ) : items.length === 0 ? (
          <EmptyState icon={Search} title="No matching vehicle events" hint="Loosen the filters and try again." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase" }}>
                  <th style={th}>Time</th><th style={th}>Plate</th><th style={th}>Camera</th>
                  <th style={th}>Type / conf</th><th style={th}>Watchlist</th><th style={th}>Links</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.event_id} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ ...td, color: C.muted, whiteSpace: "nowrap" }}>{fmtDateTime(r.timestamp)}</td>
                    <td style={td}>
                      <Link to={`/investigation?plate=${r.plate_number_normalized}`}
                            style={{ color: C.amber, fontFamily: "monospace", textDecoration: "none" }}>
                        {r.plate_number_normalized}
                      </Link>
                    </td>
                    <td style={{ ...td, color: C.muted }}>
                      {r.camera_code || "—"}
                      {r.is_mock_camera && <span style={{ color: C.violet, fontSize: 8, marginLeft: 4 }}>MOCK</span>}
                      {r.location_desc ? <div style={{ fontSize: 9 }}>{r.location_desc}</div> : null}
                    </td>
                    <td style={{ ...td, color: C.muted }}>
                      {r.vehicle_type || "—"}
                      {r.confidence_score != null ? ` · ${(r.confidence_score * 100).toFixed(0)}%` : ""}
                    </td>
                    <td style={td}>
                      {r.is_watchlisted
                        ? <SeverityBadge s="high" />
                        : <span style={{ color: C.dim }}>—</span>}
                      {r.watchlist_category ? <div style={{ fontSize: 9, color: C.muted }}>{r.watchlist_category}</div> : null}
                    </td>
                    <td style={{ ...td }}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {r.alert_id && <span style={{ color: C.red, fontSize: 9 }}>ALERT {r.alert_status}</span>}
                        {r.incident_number && (
                          <Link to={`/incidents/${r.incident_id}`} style={{ color: C.accent, fontSize: 9, textDecoration: "none" }}>
                            {r.incident_number}
                          </Link>
                        )}
                        {r.case_number && (
                          <Link to={`/cases/${r.case_id}`} style={{ color: C.violet, fontSize: 9, textDecoration: "none" }}>
                            {r.case_number}
                          </Link>
                        )}
                        {!r.alert_id && !r.incident_number && !r.case_number && (
                          <span style={{ color: C.dim, fontSize: 9 }}>—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {res && <Pager offset={offset} total={res.total} onPage={setOffset} loading={loading} page={PAGE} />}
    </div>
  );
}

function In({ label, v, on, type = "text", mono }) {
  return (
    <label style={{ fontSize: 10, color: C.muted, display: "flex", flexDirection: "column", gap: 3 }}>
      {label}
      <input type={type} value={v} onChange={(e) => on(e.target.value)}
             style={{ ...input, fontFamily: mono ? "monospace" : "inherit" }} />
    </label>
  );
}
function Sel({ label, v, on, opts }) {
  return (
    <label style={{ fontSize: 10, color: C.muted, display: "flex", flexDirection: "column", gap: 3 }}>
      {label}
      <select value={v} onChange={(e) => on(e.target.value)} style={input}>
        {opts.map((o) => <option key={o} value={o}>{o === "" ? "Any" : o}</option>)}
      </select>
    </label>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const th = { padding: "9px 12px" };
const td = { padding: "9px 12px", verticalAlign: "top" };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 7px", fontSize: 11 };
const btn = { display: "inline-flex", alignItems: "center", gap: 5, background: "transparent", border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "6px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer" };
const primaryBtn = { ...btn, background: C.accent, color: "#0b0f14", border: "none" };
const linkBtn = { background: "transparent", border: "none", cursor: "pointer", padding: 0, fontSize: 11, display: "inline-flex", alignItems: "center" };
