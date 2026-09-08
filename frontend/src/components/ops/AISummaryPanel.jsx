import { useState } from "react";
import { Sparkles } from "lucide-react";
import { C } from "../../theme.js";
import { useToast } from "../../context/ToastContext.jsx";
import ConfidenceBadge from "./ConfidenceBadge.jsx";
import { fmtDateTime } from "../../utils/datetime.js";

// "Generate AI Summary" for an incident / case (Phase 12 §3). Deterministic
// structured summary from existing rows — clearly labelled, never
// hallucinated, missing data stated as "Not available in recorded evidence."
export default function AISummaryPanel({ loader }) {
  const { push } = useToast();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setData(await loader());
    } catch (e) {
      push({ title: "AI summary failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {!data ? (
        <div style={{ padding: 12 }}>
          <button onClick={run} disabled={busy} style={btn}>
            <Sparkles size={13} /> {busy ? "Generating…" : "Generate AI Summary"}
          </button>
          <div style={{ color: C.dim, fontSize: 10, marginTop: 6 }}>
            Deterministic summary from recorded data. No external model required.
          </div>
        </div>
      ) : (
        <div style={{ padding: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
            <span style={{ fontSize: 9, fontWeight: 700, color: C.accent, letterSpacing: 0.8 }}>
              AI-GENERATED SUMMARY
            </span>
            <ConfidenceBadge level={data.confidence_level} />
            <span style={{ color: C.dim, fontSize: 10 }}>{data.provider} · {fmtDateTime(data.generated_at)}</span>
            <button onClick={run} disabled={busy} style={{ ...btn, marginLeft: "auto", padding: "4px 10px", fontSize: 10 }}>
              Regenerate
            </button>
          </div>

          <div style={{ fontSize: 13, color: C.text, lineHeight: 1.55, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 12px" }}>
            {data.headline}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 6, marginTop: 10 }}>
            {data.sections.map((s, i) => (
              <div key={i} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 5, padding: "6px 9px" }}>
                <div style={{ fontSize: 9, color: C.dim, textTransform: "uppercase", letterSpacing: 0.5 }}>
                  {s.label} {s.is_fact ? "" : "· inferred"}
                </div>
                <div style={{ fontSize: 11.5, color: C.text, marginTop: 2 }}>{s.value}</div>
              </div>
            ))}
          </div>

          {data.investigation_gaps.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: C.amber, letterSpacing: 0.8, marginBottom: 4 }}>
                INVESTIGATION GAPS
              </div>
              {data.investigation_gaps.map((g, i) => (
                <div key={i} style={{ color: C.amber, fontSize: 11, padding: "1px 0" }}>• {g}</div>
              ))}
            </div>
          )}

          <div style={{ color: C.dim, fontSize: 10, marginTop: 10 }}>{data.disclaimer}</div>
        </div>
      )}
    </div>
  );
}

const btn = { display: "inline-flex", alignItems: "center", gap: 6, background: C.accent, color: "#0b0f14", border: "none", borderRadius: 5, padding: "7px 14px", fontSize: 11.5, fontWeight: 700, cursor: "pointer" };
