import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { C } from "../theme.js";
import AlertFeed from "../components/AlertFeed.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";

const FILTERS = ["All", "Critical", "High", "Medium", "Low"];

export default function AlertsPage() {
  const { alerts, loading, backendLive, retrying, reload, critCount, ackAlert, ackAll } = useOutletContext();
  const [filter, setFilter] = useState("All");

  const unackCount = alerts.filter((a) => !a.ack).length;
  const visible = filter === "All" ? alerts : alerts.filter((a) => a.severity === filter.toLowerCase());

  return (
    <div>
      {!backendLive && (
        <ErrorBanner message="Backend connection lost — showing simulated data. Retrying…" onRetry={reload} retrying={retrying} />
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontWeight: 600 }}>
          Alert Log — {alerts.length} total, {unackCount} unacknowledged
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                background: f === filter ? C.accentGlow : "transparent",
                border: `1px solid ${f === filter ? C.accent : C.border}`,
                color: f === filter ? C.accent : C.muted,
                borderRadius: 4,
                padding: "4px 12px",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <AlertFeed
          alerts={visible}
          loading={loading}
          critCount={critCount}
          onAck={ackAlert}
          onAckAll={ackAll}
          maxHeight="calc(100vh - 240px)"
          title={filter === "All" ? "All Alerts" : `${filter} Alerts`}
        />
      </div>
    </div>
  );
}
