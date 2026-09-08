import { useEffect, useState } from "react";
import { C } from "../../theme.js";
import { SkeletonRows } from "../ui/Skeleton.jsx";
import EmptyState from "../ui/EmptyState.jsx";
import { Clock } from "lucide-react";
import { fmtDateTime, fmtTime } from "../../utils/datetime.js";

const CAT_COLOR = {
  ALERT: C.red,
  INCIDENT: C.amber,
  CASE: C.accent,
  EVIDENCE: C.violet,
  NOTE: C.muted,
  VEHICLE: C.green,
  STATUS: C.accent,
  ACTIVITY: C.muted,
};

// Chronological timeline (Phase 11 FEATURE 7 / 8). Fetches from a loader that
// takes an optional category filter; the backend derives every entry from
// existing rows (audit log, notes, evidence, sightings).
export default function Timeline({ loader, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("ALL");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader(filter === "ALL" ? undefined : filter)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData({ entries: [], categories: [] }))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [loader, filter, refreshKey]);

  const cats = data?.categories || [];
  const entries = data?.entries || [];

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {["ALL", ...cats].map((c) => (
          <button
            key={c}
            onClick={() => setFilter(c)}
            style={{
              background: filter === c ? C.accentGlow : "transparent",
              border: `1px solid ${filter === c ? C.accent : C.border}`,
              color: filter === c ? C.accent : C.muted,
              borderRadius: 3, padding: "2px 9px", fontSize: 10, fontWeight: 600,
              textTransform: "uppercase", letterSpacing: 0.5, cursor: "pointer",
            }}
          >
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonRows rows={5} height={34} />
      ) : entries.length === 0 ? (
        <EmptyState icon={Clock} title="No timeline entries" hint="Activity on this record will appear here." />
      ) : (
        <div style={{ position: "relative", paddingLeft: 14 }}>
          <div style={{ position: "absolute", left: 4, top: 4, bottom: 4, width: 2, background: C.border }} />
          {entries.map((e, i) => {
            const color = CAT_COLOR[e.category] || C.muted;
            return (
              <div key={i} style={{ position: "relative", paddingBottom: 12 }}>
                <span style={{
                  position: "absolute", left: -14, top: 3, width: 9, height: 9, borderRadius: "50%",
                  background: color, border: `2px solid ${C.surface}`,
                }} />
                <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                  <span style={{ color, fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {e.category}
                  </span>
                  <span style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{e.action}</span>
                  {e.actor && <span style={{ color: C.muted, fontSize: 10 }}>· {e.actor}</span>}
                  <span style={{ color: C.dim, fontSize: 10, fontFamily: "monospace", marginLeft: "auto" }}
                        title={fmtDateTime(e.timestamp)}>
                    {fmtDateTime(e.timestamp)} {fmtTime(e.timestamp)}
                  </span>
                </div>
                {e.detail && <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{e.detail}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
