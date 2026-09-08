import { useEffect, useState } from "react";
import { ScanFace } from "lucide-react";
import { C } from "../../theme.js";
import { fmtDateTime } from "../../utils/datetime.js";
import { http } from "../../services/api.js";

const BAND_COLOR = { STRONG: C.green, MODERATE: C.amber, WEAK: C.muted, NONE: C.dim };

// Phase 14 §1/§11 — Visual Matches tab for the Vehicle Investigation
// console. Appearance-similar sightings from the Re-ID index. Visual
// similarity is NOT identity — every row is labelled VISUAL MATCH with an
// explicit similarity % and a capped confidence.
export default function VisualMatchesPanel({ plate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!plate) return;
    setLoading(true);
    setErr("");
    http
      .post("/ai/reid/search", { plate, limit: 12, exclude_same_plate: false })
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.error?.message || "Re-ID search failed"))
      .finally(() => setLoading(false));
  }, [plate]);

  return (
    <section style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", marginBottom: 12 }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <ScanFace size={13} color={C.accent} />
        <span style={{ fontWeight: 600, fontSize: 12 }}>Visual Matches</span>
        <span style={{ fontSize: 8, fontWeight: 700, color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 4px" }}>AI</span>
        <span style={{ color: C.muted, fontWeight: 400, fontSize: 10, marginLeft: "auto" }}>
          {data ? `${data.returned} of ${data.scanned} scanned` : ""}
        </span>
      </div>
      <div style={{ padding: 12 }}>
        {loading ? (
          <div style={{ color: C.dim, fontSize: 11 }}>Searching appearance index…</div>
        ) : err ? (
          <div style={{ color: C.red, fontSize: 11 }}>{err}</div>
        ) : !data?.candidates?.length ? (
          <div style={{ color: C.dim, fontSize: 11 }}>No appearance-similar sightings found.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {data.candidates.map((c) => (
              <div key={c.event_id} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 11, borderLeft: `3px solid ${c.same_plate ? C.green : C.amber}`, background: C.panel, borderRadius: 5, padding: "6px 9px" }}>
                <span style={{ fontSize: 8, fontWeight: 800, color: c.same_plate ? C.green : C.amber, letterSpacing: 0.5 }}>
                  {c.verdict}
                </span>
                <span style={{ fontFamily: "monospace", color: C.accent }}>{c.camera_code}</span>
                <span style={{ color: C.muted, fontFamily: "monospace" }}>{fmtDateTime(c.timestamp)}</span>
                <span style={{ color: C.text }}>plate <b>{c.plate_number_normalized}</b></span>
                {c.vehicle_type && <span style={{ color: C.dim }}>{c.vehicle_type}</span>}
                {c.vehicle_color && <span style={{ color: C.dim }}>{c.vehicle_color}</span>}
                <span style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontFamily: "monospace", color: C.text }}>{c.similarity_pct}%</span>
                  <span style={{ color: BAND_COLOR[c.band] || C.muted, fontWeight: 700 }}>{c.band}</span>
                  <span style={{ color: C.muted, fontSize: 9 }}>conf {c.confidence_level}</span>
                </span>
              </div>
            ))}
          </div>
        )}
        {data && (
          <div style={{ color: C.dim, fontSize: 9, marginTop: 8 }}>
            {data.disclaimer}
          </div>
        )}
      </div>
    </section>
  );
}
