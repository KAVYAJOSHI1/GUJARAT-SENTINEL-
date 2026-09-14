import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Body, MonoLabel } from "../components/Text.jsx";
import { theme, REAL_DEMO } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

const STATS = [
  { v: REAL_DEMO.camerasLive, l: "cameras live" },
  { v: REAL_DEMO.anprConfidence, l: "anpr confidence" },
  { v: REAL_DEMO.alertLatency, l: "alert latency" },
  { v: REAL_DEMO.hallucinatedPlates, l: "hallucinated plates" },
];

function StatCell({ stat, delay }) {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - delay, [0, 12], [0, 1], clamp);
  const y = interpolate(frame - delay, [0, 12], [10, 0], clamp);
  return (
    <div style={{ opacity, transform: `translateY(${y}px)`, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <div style={{ fontFamily: theme.fontMono, fontSize: 34, color: theme.accent, fontVariantNumeric: "tabular-nums" }}>{stat.v}</div>
      <MonoLabel delay={0} size={11} color={theme.text2}>{stat.l}</MonoLabel>
    </div>
  );
}

export function Scene6Proof({ durationInFrames }) {
  const frame = useCurrentFrame();
  return (
    <SceneShell durationInFrames={durationInFrames}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 46 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <Body size={26} color={theme.text} delay={6}>This isn&rsquo;t a mockup.</Body>
          <Body size={26} color={theme.text2} delay={26}>
            It&rsquo;s a real YOLOv8 + OCR detection pipeline, built to run on
            the camera network that already exists.
          </Body>
        </div>
        <div style={{ display: "flex", gap: 70, padding: "10px 40px", borderTop: `1px solid ${theme.text3}`, borderBottom: `1px solid ${theme.text3}` }}>
          {STATS.map((s, i) => <StatCell key={s.l} stat={s} delay={70 + i * 14} />)}
        </div>
        <div style={{ opacity: interpolate(frame, [150, 170], [0, 1], clamp) }}>
          <MonoLabel delay={0} color={theme.text3} size={11}>figures from the platform&rsquo;s own seeded verification run</MonoLabel>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
