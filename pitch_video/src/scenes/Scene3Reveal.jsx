import { AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Headline, MonoLabel } from "../components/Text.jsx";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

function Node({ children, label, active, x }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, opacity: active, position: "relative", left: x }}>
      <div
        style={{
          width: 96,
          height: 96,
          borderRadius: 14,
          border: `1.5px solid ${theme.accent}`,
          background: "rgba(94,207,184,0.06)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: `0 0 24px rgba(94,207,184,0.18)`,
        }}
      >
        {children}
      </div>
      <MonoLabel delay={0} size={11.5}>{label}</MonoLabel>
    </div>
  );
}

const CameraIcon = () => (
  <svg width="42" height="42" viewBox="0 0 24 24" fill="none">
    <rect x="2" y="7" width="14" height="11" rx="2" stroke={theme.accentLight} strokeWidth="1.6" />
    <path d="M16 10.5L22 7v10l-6-3.5" stroke={theme.accentLight} strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);
const ScanIcon = ({ frame, start }) => {
  const t = interpolate(frame, [start, start + 40], [0, 1], clamp);
  return (
    <svg width="46" height="46" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke={theme.text3} strokeWidth="1.2" strokeDasharray="2 2" />
      <path d="M4 14h16" stroke={theme.accent} strokeWidth="1.8" style={{ transform: `translateY(${(t - 0.5) * 12}px)` }} />
    </svg>
  );
};
const PlateIcon = ({ frame, start }) => {
  const chars = "GJ18TC0450";
  const shown = Math.round(interpolate(frame, [start, start + 40], [0, chars.length], clamp));
  return (
    <div style={{ fontFamily: theme.fontMono, fontSize: 13, color: theme.text, letterSpacing: 1 }}>
      {chars.slice(0, shown)}
      <span style={{ opacity: 0.35 }}>{chars.slice(shown)}</span>
    </div>
  );
};
const CheckIcon = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="9.5" stroke={theme.green} strokeWidth="1.6" />
    <path d="M7.5 12.5l3 3 6-6.5" stroke={theme.green} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function Pipeline({ frame }) {
  const n1 = interpolate(frame, [50, 66], [0, 1], clamp);
  const n2 = interpolate(frame, [110, 126], [0, 1], clamp);
  const n3 = interpolate(frame, [190, 206], [0, 1], clamp);
  const n4 = interpolate(frame, [280, 296], [0, 1], clamp);
  const line = (from, to, active) => (
    <div style={{ flex: 1, height: 1.5, alignSelf: "center", background: theme.viridian, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: theme.accent, transform: `scaleX(${active})`, transformOrigin: "left" }} />
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, width: 900 }}>
      <Node label="CAMERA" active={n1}><CameraIcon /></Node>
      {line(1, 2, interpolate(frame, [66, 110], [0, 1], clamp))}
      <Node label="AI DETECTION" active={n2}><ScanIcon frame={frame} start={126} /></Node>
      {line(2, 3, interpolate(frame, [140, 190], [0, 1], clamp))}
      <Node label="PLATE READ" active={n3}><PlateIcon frame={frame} start={206} /></Node>
      {line(3, 4, interpolate(frame, [220, 280], [0, 1], clamp))}
      <Node label="WATCHLIST MATCH" active={n4}><CheckIcon /></Node>
    </div>
  );
}

export function Scene3Reveal({ durationInFrames }) {
  const frame = useCurrentFrame();
  const logoOpacity = interpolate(frame, [0, 20, 300, 340], [0, 1, 1, 0.15], clamp);
  const logoScale = interpolate(frame, [0, 30], [0.9, 1], clamp);
  const pipelineOpacity = interpolate(frame, [40, 60], [0, 1], clamp);
  const ghostOpacity = interpolate(frame, [0, 40, 340], [0, 0.05, 0.02], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div
          style={{
            position: "absolute",
            fontFamily: theme.fontDisplay,
            fontSize: 260,
            color: theme.accent,
            opacity: ghostOpacity,
            letterSpacing: 6,
            whiteSpace: "nowrap",
          }}
        >
          SENTINEL
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 44 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, opacity: logoOpacity, transform: `scale(${logoScale})` }}>
            <Img src={staticFile("logo.png")} style={{ width: 54, height: 54, objectFit: "contain" }} />
            <Headline size={40} delay={4}>SENTINEL</Headline>
            <MonoLabel delay={16} color={theme.accent}>AI vision for public safety</MonoLabel>
          </div>
          <div style={{ opacity: pipelineOpacity }}>
            <Pipeline frame={frame} />
          </div>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
