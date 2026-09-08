import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Marker, Popup } from "react-leaflet";
import L from "leaflet";
import { Bot, CornerDownLeft, MapPin, Sparkles } from "lucide-react";
import { C } from "../theme.js";
import { useToast } from "../context/ToastContext.jsx";
import { aiInvestigate, aiStatus, aiSuggestions, runInvestigation } from "../services/aiApi.js";
import GisMap from "../components/gis/GisMap.jsx";
import ConfidenceBadge from "../components/ops/ConfidenceBadge.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const dot = L.divIcon({
  className: "",
  html: `<span style="display:block;width:12px;height:12px;border-radius:50%;background:${C.accent};border:2px solid #0b0f14;box-shadow:0 0 6px ${C.accent}"></span>`,
  iconSize: [12, 12],
});

// Investigation Copilot (Phase 12 §1). Natural-language questions ->
// deterministic parse -> validated tools -> real Sentinel data. The AI
// never invents a result; every answer shows the parsed filters + a
// FACT/INFERENCE confidence marker.
export default function CopilotPage() {
  const navigate = useNavigate();
  const { push } = useToast();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const contextPlate = params.get("plate") || undefined;
  const [thread, setThread] = useState([]);
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(false);
  const [deep, setDeep] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    aiSuggestions().then(setSuggestions);
    aiStatus().then(setStatus).catch(() => {});
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [thread, busy]);

  const ask = useCallback(async (text) => {
    const query = (text ?? q).trim();
    if (!query || busy) return;
    setBusy(true);
    setError(false);
    const wantsDeep = deep || /\binvestigate\b/i.test(query);
    setThread((t) => [...t, { role: "user", text: query }]);
    setQ("");
    try {
      if (wantsDeep) {
        const report = await runInvestigation(query, contextPlate);
        setThread((t) => [...t, { role: "agent", report }]);
      } else {
        const res = await aiInvestigate(query, contextPlate);
        setThread((t) => [...t, { role: "ai", res }]);
      }
    } catch (e) {
      setError(true);
      push({ title: "Copilot request failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
    }
  }, [q, busy, contextPlate, deep, push]);

  // auto-run a deep-linked question once
  const ran = useRef(false);
  useEffect(() => {
    if (params.get("q") && !ran.current) { ran.current = true; ask(params.get("q")); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 1000, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Bot size={17} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Investigation Copilot</span>
        {status && (
          <span style={{ color: C.muted, fontSize: 10, border: `1px solid ${C.border}`, borderRadius: 3, padding: "1px 6px" }}>
            {status.provider}{status.llm_available ? " · LLM" : " · offline-capable"}
          </span>
        )}
      </div>
      <div style={{ color: C.muted, fontSize: 11 }}>
        Ask about vehicles, journeys, cameras, alerts, incidents, cases or evidence. Answers use
        recorded Sentinel data only — the AI never invents results.
      </div>

      {error && <ErrorBanner message="The Copilot could not answer that. Try rephrasing." />}

      {thread.length === 0 && (
        <div style={panel}>
          <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 6 }}>
            <Sparkles size={12} color={C.accent} /> Try one of these
          </div>
          <div style={{ padding: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {suggestions.map((s) => (
              <button key={s} onClick={() => ask(s)} style={chip}>{s}</button>
            ))}
          </div>
        </div>
      )}

      {thread.map((m, i) =>
        m.role === "user" ? (
          <div key={i} style={{ alignSelf: "flex-end", background: C.accentGlow, border: `1px solid ${C.accent}55`, borderRadius: "10px 10px 2px 10px", padding: "8px 12px", fontSize: 13, maxWidth: "80%" }}>
            {m.text}
          </div>
        ) : m.role === "agent" ? (
          <AgentReportCard key={i} report={m.report} navigate={navigate} />
        ) : (
          <AnswerCard key={i} res={m.res} navigate={navigate} />
        )
      )}
      {busy && <div style={{ color: C.muted, fontSize: 12, padding: "4px 2px" }}>Investigating…</div>}
      <div ref={endRef} />

      <form
        onSubmit={(e) => { e.preventDefault(); ask(); }}
        style={{ position: "sticky", bottom: 0, display: "flex", gap: 8, background: C.bg, padding: "8px 0" }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask the Copilot… e.g. Where was GJ18TC0450 seen in the last 6 hours?"
          style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: "10px 12px", fontSize: 13 }}
        />
        <label style={{ display: "flex", alignItems: "center", gap: 5, color: deep ? C.accent : C.muted, fontSize: 10, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}
               title="Run the multi-step investigation agent (search + journey + visual matches + correlation + alerts + anomalies + incidents + cases + evidence + gap detection)">
          <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} /> DEEP
        </label>
        <button type="submit" disabled={busy || !q.trim()} style={{ ...primaryBtn }}>
          <CornerDownLeft size={13} /> {deep ? "Investigate" : "Ask"}
        </button>
      </form>
    </div>
  );
}

const GAP_COLOR = { high: "#E0574C", medium: "#D9A441", low: "#8993A1" };

function AgentReportCard({ report, navigate }) {
  const [showSteps, setShowSteps] = useState(false);
  return (
    <div style={{ ...panel, borderColor: `${C.violet}55` }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
          <span style={{ fontSize: 9, fontWeight: 800, color: C.violet, letterSpacing: 0.8 }}>
            AI INVESTIGATION AGENT
          </span>
          <span style={{ fontSize: 8, fontWeight: 700, color: C.green, border: `1px solid ${C.green}`, borderRadius: 3, padding: "0 4px" }}>
            READ-ONLY
          </span>
          <ConfidenceBadge level={report.confidence_level} score={report.confidence_score} method={`plan: ${report.plan_source}`} />
          <span style={{ marginLeft: "auto", color: C.dim, fontSize: 10 }}>
            {report.steps?.length || 0} step(s) · {report.provider}
          </span>
        </div>
        <div style={{ fontSize: 13.5, color: C.text, lineHeight: 1.5 }}>{report.summary}</div>
      </div>

      {(report.sections || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12, display: "grid", gap: 8 }}>
          {report.sections.map((s, i) => (
            <div key={i}>
              <div style={{ fontSize: 9, fontWeight: 700, color: C.muted, letterSpacing: 0.6, textTransform: "uppercase" }}>{s.title}</div>
              <div style={{ fontSize: 12, color: C.text, marginTop: 2 }}>{s.body}</div>
            </div>
          ))}
        </div>
      )}

      {(report.gaps || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: C.amber, letterSpacing: 0.8, marginBottom: 6 }}>
            INVESTIGATION GAPS ({report.gaps.length}) — evidence/coverage warnings, not accusations
          </div>
          {report.gaps.map((g, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 11, padding: "3px 0" }}>
              <span style={{ color: GAP_COLOR[g.severity] || C.muted, fontWeight: 700, minWidth: 92, fontSize: 9 }}>
                {g.kind}
              </span>
              <span style={{ color: C.muted }}>{g.description}</span>
            </div>
          ))}
        </div>
      )}

      {(report.related || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {report.related.map((r) => (
            <Link key={r.kind + r.id} to={r.href} style={{ ...chip, color: C.accent, textDecoration: "none" }}>
              {r.kind}: {r.label}
            </Link>
          ))}
        </div>
      )}

      <div style={{ borderTop: `1px solid ${C.border}`, padding: "8px 12px", display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button style={{ ...chip }} onClick={() => setShowSteps((v) => !v)}>
          {showSteps ? "Hide" : "Show"} agent steps
        </button>
        {report.plate && (
          <button style={{ ...chip, color: C.accent }} onClick={() => navigate(`/investigation?plate=${report.plate}`)}>
            <MapPin size={11} /> Open full investigation & GIS
          </button>
        )}
      </div>
      {showSteps && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12 }}>
          {report.steps.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 10.5, padding: "2px 0", color: s.error ? C.red : s.skipped ? C.dim : C.muted }}>
              <span style={{ color: C.accent, minWidth: 150, fontFamily: "monospace" }}>{s.tool}</span>
              <span>{s.error ? `error: ${s.error}` : s.skipped ? `skipped (${s.reason})` : s.result_summary}</span>
            </div>
          ))}
        </div>
      )}
      <div style={{ padding: "8px 12px", borderTop: `1px solid ${C.border}`, color: C.dim, fontSize: 9.5 }}>
        {report.disclaimer}
      </div>
    </div>
  );
}

function AnswerCard({ res, navigate }) {
  const p = res.parsed || {};
  const mapPts = res.map_points || [];
  return (
    <div style={{ ...panel, borderColor: `${C.accent}44` }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: C.muted, letterSpacing: 0.8 }}>
            {res.intent?.replace(/_/g, " ")}
          </span>
          <ConfidenceBadge level={res.confidence_level} score={res.confidence_score} method={res.match_method} />
          <span style={{ marginLeft: "auto", color: C.dim, fontSize: 10 }}>{res.result_count} result(s)</span>
        </div>
        <div style={{ fontSize: 13.5, color: C.text, lineHeight: 1.5 }}>{res.answer}</div>

        {/* interpreted filters — explainability */}
        <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 5 }}>
          {p.plate && <Tag>plate: {p.plate}</Tag>}
          {(p.camera_codes || []).map((c) => <Tag key={c}>{c}</Tag>)}
          {p.vehicle_type && <Tag>{p.vehicle_type}</Tag>}
          {p.vehicle_color && <Tag>{p.vehicle_color}</Tag>}
          {p.relative_window && <Tag>{p.relative_window}</Tag>}
          {p.time_from && <Tag>after {p.time_from}</Tag>}
          {p.time_to && <Tag>before {p.time_to}</Tag>}
          {p.min_duration_seconds && <Tag>≥ {Math.round(p.min_duration_seconds / 60)} min dwell</Tag>}
          {p.watchlist_only && <Tag>watchlist</Tag>}
          {p.unknown_only && <Tag>unknown plates</Tag>}
        </div>

        {(res.limitations || []).length > 0 && (
          <div style={{ marginTop: 6, color: C.amber, fontSize: 10.5 }}>
            {res.limitations.map((l, i) => <div key={i}>• {l}</div>)}
          </div>
        )}
      </div>

      {mapPts.length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}` }}>
          <GisMap
            center={[mapPts[0].latitude, mapPts[0].longitude]}
            zoom={12}
            height={240}
            focus={{ lat: mapPts[0].latitude, lng: mapPts[0].longitude, zoom: 12 }}
          >
            {mapPts.map((mp, i) => (
              <Marker key={i} position={[mp.latitude, mp.longitude]} icon={dot}>
                <Popup>{mp.label}</Popup>
              </Marker>
            ))}
          </GisMap>
        </div>
      )}

      {(res.timeline || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: C.muted, letterSpacing: 0.8, marginBottom: 6 }}>TIMELINE</div>
          {res.timeline.map((t, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 11, alignItems: "baseline", padding: "2px 0" }}>
              <span style={{ color: C.dim, fontFamily: "monospace", minWidth: 118 }}>{fmtDateTime(t.timestamp)}</span>
              <span style={{ color: C.accent, minWidth: 62 }}>{t.camera_code || ""}</span>
              <span style={{ color: C.text }}>{t.label}</span>
            </div>
          ))}
        </div>
      )}

      {(res.related || []).length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {res.related.map((r) => (
            <Link key={r.kind + r.id} to={r.href} style={{ ...chip, color: C.accent, textDecoration: "none" }}>
              {r.kind}: {r.label}
            </Link>
          ))}
        </div>
      )}

      {p.plate && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: "8px 12px" }}>
          <button style={{ ...chip, color: C.accent }} onClick={() => navigate(`/investigation?plate=${p.plate}`)}>
            <MapPin size={11} /> Open full investigation & GIS
          </button>
        </div>
      )}
    </div>
  );
}

const Tag = ({ children }) => (
  <span style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted, borderRadius: 3, padding: "1px 7px", fontSize: 10 }}>{children}</span>
);
const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const chip = { display: "inline-flex", alignItems: "center", gap: 5, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 10px", fontSize: 11, cursor: "pointer" };
const primaryBtn = { display: "inline-flex", alignItems: "center", gap: 6, background: C.accent, color: "#0b0f14", border: "none", borderRadius: 6, padding: "10px 16px", fontSize: 12, fontWeight: 700, cursor: "pointer" };
