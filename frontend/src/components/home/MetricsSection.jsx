import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// Illustrative dummy series — presentation-layer only, styled after the
// reference site's own telemetry charts. Not read off the live app (this
// page renders before authentication, so it has no live session to query);
// clearly framed below as illustrative, not a captured screenshot.
function smoothSeries(n, base, spread, seed) {
  let v = base;
  const out = [];
  for (let i = 0; i < n; i++) {
    v += Math.sin(i * 0.7 + seed) * spread * 0.5 + (Math.random() - 0.5) * spread * 0.3;
    out.push(Math.max(0, v));
  }
  return out;
}

const ANPR_READS = smoothSeries(24, 40, 14, 1);
const UPTIME = smoothSeries(24, 97, 2, 2).map((v) => Math.min(100, v));
const SEVERITY_BARS = [3, 7, 2, 9, 4, 8, 5, 6, 3, 7, 9, 4];
const CONFIDENCE_BUCKETS = [2, 4, 9, 22, 41, 63, 58, 33, 12];

function LineChart({ data, color, w = 300, h = 110 }) {
  const max = Math.max(...data) * 1.15 || 1;
  const step = w / (data.length - 1);
  const points = data.map((v, i) => `${i * step},${h - (v / max) * h}`).join(" ");
  const area = `0,${h} ${points} ${w},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="hp-chart-svg" preserveAspectRatio="none">
      <polygon points={area} fill={color} opacity="0.12" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.6" />
    </svg>
  );
}

function BarChart({ data, color, w = 300, h = 110 }) {
  const max = Math.max(...data) * 1.1 || 1;
  const gap = 4;
  const bw = w / data.length - gap;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="hp-chart-svg" preserveAspectRatio="none">
      {data.map((v, i) => {
        const bh = (v / max) * h;
        return (
          <rect key={i} x={i * (bw + gap)} y={h - bh} width={bw} height={bh} fill={color} opacity="0.85" rx="1" />
        );
      })}
    </svg>
  );
}

const PANELS = [
  { title: "ANPR Reads · 30 Days", sub: "Plate reads across all live cameras", kind: "line", data: ANPR_READS, color: "#5ecfb8" },
  { title: "Alerts by Severity · 14 Days", sub: "Watchlist hits + AI anomaly events", kind: "bar", data: SEVERITY_BARS, color: "#e8a045" },
  { title: "Camera Uptime % · 30 Days", sub: "Network-wide online percentage", kind: "line", data: UPTIME, color: "#5ecfb8" },
  { title: "OCR Confidence Distribution", sub: "Readable-plate confidence buckets", kind: "bar", data: CONFIDENCE_BUCKETS, color: "#8ee4d0" },
];

export default function MetricsSection() {
  const rootRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-metrics-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });
      gsap.from(".hp-chart-panel", {
        opacity: 0, y: 34, duration: 0.6, ease: "power2.out", stagger: 0.1,
        scrollTrigger: { trigger: ".hp-chart-grid", start: "top 82%" },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="hp-section hp-metrics">
      <div className="hp-ghost-word" aria-hidden="true">PULSE</div>
      <div className="hp-metrics-heading">
        <div className="hp-eyebrow">TELEMETRY</div>
        <h2 className="hp-h2">The pulse of the network.</h2>
        <p className="hp-lede">
          Illustrative of the shape of SENTINEL's own analytics (ANPR Intelligence, Alerts,
          Camera Health) — not a live feed on this page, since it renders before sign-in.
        </p>
      </div>
      <div className="hp-chart-grid">
        {PANELS.map((p) => (
          <div key={p.title} className="hp-chart-panel hp-bracket-panel">
            <div className="hp-chart-title">{p.title}</div>
            <div className="hp-chart-sub">{p.sub}</div>
            {p.kind === "line" ? (
              <LineChart data={p.data} color={p.color} />
            ) : (
              <BarChart data={p.data} color={p.color} />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
