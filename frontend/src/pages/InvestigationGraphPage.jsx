import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Network, Search } from "lucide-react";
import { C } from "../theme.js";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { investigationGraph } from "../services/graphApi.js";

const TYPE_COLOR = {
  vehicle: C.accent, detection: "#6FB1E0", camera: C.violet, location: "#7d8aa0",
  alert: C.red, anomaly: "#E08A4C", incident: C.amber, evidence: "#5Fb37F",
  case: C.green, watchlist: "#E0574C",
};
const COL_W = 210;
const ROW_H = 62;

// Phase 14 §12 — Investigation Graph. Deterministic, built only from
// persisted records. BFS-layered layout; every node opens its Sentinel
// entity page.
export default function InvestigationGraphPage() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [plate, setPlate] = useState(params.get("plate") || "");
  const [q, setQ] = useState(params.get("plate") || "");
  const [g, setG] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!plate) return;
    setLoading(true);
    setErr("");
    investigationGraph(plate)
      .then(setG)
      .catch((e) => setErr(e?.response?.data?.error?.message || "Failed to build graph"))
      .finally(() => setLoading(false));
  }, [plate]);

  const layout = useMemo(() => {
    if (!g?.nodes?.length) return null;
    const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    const adj = {};
    g.nodes.forEach((n) => (adj[n.id] = []));
    g.edges.forEach((e) => {
      if (adj[e.source] && adj[e.target]) {
        adj[e.source].push(e.target);
        adj[e.target].push(e.source);
      }
    });
    // BFS depth from root
    const depth = { [g.root]: 0 };
    const queue = [g.root];
    while (queue.length) {
      const cur = queue.shift();
      for (const nb of adj[cur]) {
        if (depth[nb] === undefined) { depth[nb] = depth[cur] + 1; queue.push(nb); }
      }
    }
    g.nodes.forEach((n) => { if (depth[n.id] === undefined) depth[n.id] = 6; });
    const cols = {};
    g.nodes
      .slice()
      .sort((a, b) => (a.type + a.label).localeCompare(b.type + b.label))
      .forEach((n) => {
        const d = depth[n.id];
        (cols[d] = cols[d] || []).push(n);
      });
    const pos = {};
    Object.entries(cols).forEach(([d, ns]) => {
      ns.forEach((n, i) => {
        pos[n.id] = { x: 40 + Number(d) * COL_W, y: 40 + i * ROW_H };
      });
    });
    const maxCol = Math.max(...Object.keys(cols).map(Number));
    const maxRow = Math.max(...Object.values(cols).map((c) => c.length));
    return { pos, byId, width: 80 + (maxCol + 1) * COL_W, height: 80 + maxRow * ROW_H };
  }, [g]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Network size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Investigation Graph</span>
        <span style={{ color: C.muted, fontSize: 11 }}>
          deterministic · built only from persisted records
        </span>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); setPlate(q.trim().toUpperCase()); setParams({ plate: q.trim().toUpperCase() }); }}
        style={{ display: "flex", gap: 8, margin: "10px 0 14px", maxWidth: 420 }}
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Registration plate…"
          style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: "8px 12px", fontSize: 13, fontFamily: "monospace" }} />
        <button type="submit" style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.accent, color: "#0b0f14", border: "none", borderRadius: 6, padding: "8px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
          <Search size={13} /> Build
        </button>
      </form>

      {err && <ErrorBanner message={err} />}
      {loading && <div style={{ color: C.muted, fontSize: 12 }}>Building graph…</div>}

      {g && !loading && (
        g.node_count <= 1 ? (
          <EmptyState icon={Network} title={`Nothing linked to ${g.subject}`}
            hint="No detections, alerts, incidents or cases reference this plate." />
        ) : (
          <>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {Object.entries(g.counts_by_type).map(([t, n]) => (
                <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: C.muted }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: TYPE_COLOR[t] || C.muted }} />
                  {t} ({n})
                </span>
              ))}
              {g.truncated && <span style={{ color: C.amber, fontSize: 10 }}>· graph truncated (bounded)</span>}
            </div>
            <div style={{ overflow: "auto", background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, maxHeight: "72vh" }}>
              <svg width={layout?.width || 600} height={layout?.height || 400}
                style={{ display: "block", minWidth: "100%" }}>
                {g.edges.map((e, i) => {
                  const a = layout?.pos[e.source]; const b = layout?.pos[e.target];
                  if (!a || !b) return null;
                  return (
                    <g key={i}>
                      <line x1={a.x + 80} y1={a.y + 16} x2={b.x} y2={b.y + 16}
                        stroke={C.border} strokeWidth={1.2} />
                      {e.label && (
                        <text x={(a.x + 80 + b.x) / 2} y={(a.y + b.y) / 2 + 12}
                          fill={C.dim} fontSize={8} textAnchor="middle">{e.label}</text>
                      )}
                    </g>
                  );
                })}
                {g.nodes.map((n) => {
                  const p = layout?.pos[n.id];
                  if (!p) return null;
                  const col = TYPE_COLOR[n.type] || C.muted;
                  return (
                    <g key={n.id} transform={`translate(${p.x},${p.y})`}
                      style={{ cursor: n.href ? "pointer" : "default" }}
                      onClick={() => n.href && nav(n.href)}>
                      <rect width={168} height={32} rx={5} fill={C.panel} stroke={col} strokeWidth={1.4} />
                      <rect width={4} height={32} rx={2} fill={col} />
                      <text x={12} y={13} fill={C.dim} fontSize={7} style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>{n.type}</text>
                      <text x={12} y={25} fill={C.text} fontSize={10} fontFamily="monospace">
                        {(n.label || "").slice(0, 22)}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <div style={{ color: C.dim, fontSize: 9.5, marginTop: 6 }}>{g.note} Click any node to open it.</div>
          </>
        )
      )}
    </div>
  );
}
