import { useEffect, useState } from "react";
import { BarChart3, Car, Clock, Hash, ScanLine, ShieldAlert } from "lucide-react";
import { C } from "../../theme.js";
import { fetchAnalyticsOverview } from "../../services/analyticsApi.js";
import MiniBarList from "./MiniBarList.jsx";

// Vehicle Intelligence — real DB aggregates (Phase 5 §4). Fetches
// /api/v1/analytics/overview on mount + when the dashboard reloads.
// Phase 5 rule: on failure it shows an explicit "unavailable" state, NEVER
// mock numbers.
const WINDOW = 24;

function Stat({ icon: Icon, label, value, color = C.text }) {
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 12px", flex: "1 1 130px" }}>
      <div style={{ color: C.muted, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 1, display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
        <Icon size={10} /> {label}
      </div>
      <div style={{ color, fontSize: 15, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{value}</div>
    </div>
  );
}

export default function VehicleIntelPanel({ reloadKey = 0 }) {
  const [state, setState] = useState({ loading: true, data: null, live: false });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    fetchAnalyticsOverview({ windowHours: WINDOW }).then((res) => {
      if (cancelled) return;
      setState({ loading: false, data: res.data, live: res.live });
    });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const { loading, data, live } = state;

  return (
    <section style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 12 }}>
          <BarChart3 size={13} color={C.accent} /> Vehicle Intelligence
          <span style={{ color: C.muted, fontWeight: 400 }}>· last {WINDOW}h · all-time totals</span>
        </span>
        {!loading && !live && (
          <span style={{ color: C.amber, fontSize: 10, border: `1px solid ${C.amber}55`, borderRadius: 3, padding: "1px 6px" }}>
            DATA UNAVAILABLE
          </span>
        )}
      </div>

      <div style={{ padding: 12 }}>
        {loading ? (
          <div style={{ color: C.dim, fontSize: 12 }}>Loading vehicle analytics…</div>
        ) : !data ? (
          <div style={{ color: C.muted, fontSize: 12 }}>
            Vehicle analytics are unavailable right now (backend unreachable). No
            estimated figures are shown.
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
              <Stat icon={ScanLine} label="Events (all-time)" value={data.totalEvents.toLocaleString("en-IN")} color={C.accent} />
              <Stat icon={Hash} label={`Distinct plates / ${WINDOW}h`} value={data.distinctPlatesInWindow} />
              <Stat icon={Car} label={`Readable reads / ${WINDOW}h`} value={data.readableInWindow} color={C.violet} />
              <Stat icon={Clock} label={`UNKNOWN / ${WINDOW}h`} value={data.unknownInWindow} color={C.muted} />
              <Stat icon={ShieldAlert} label="Watchlist matches (all-time)" value={data.watchlistMatchesTotal} color={data.watchlistMatchesTotal > 0 ? C.red : C.green} />
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <MiniBarList title="Detections by type" icon={Car} items={data.byType.slice(0, 6)} emptyHint="No classified detections yet" />
              <MiniBarList title={`Top cameras / ${WINDOW}h`} icon={BarChart3} items={data.byCamera.slice(0, 6)} emptyHint="No detections in window" />
              <MiniBarList title={`Top plates / ${WINDOW}h`} icon={Hash} items={data.topPlates.slice(0, 6)} emptyHint="No repeat plates yet" />
              <MiniBarList title={`Activity / ${WINDOW}h`} icon={Clock} items={data.byHour.slice(-8)} emptyHint="No recent activity" />
            </div>
          </>
        )}
      </div>
    </section>
  );
}
