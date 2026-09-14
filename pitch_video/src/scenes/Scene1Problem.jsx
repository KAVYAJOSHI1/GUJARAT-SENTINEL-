import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Headline, MonoLabel } from "../components/Text.jsx";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const COLS = 9;
const ROWS = 5;

// Deterministic pseudo-random per tile (no Math.random — must render
// identically every frame/pass).
function hash(i) {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function CameraGrid({ frame }) {
  const tiles = [];
  const flashIndex = 33; // the one tile that "sees" the plate and lets it go
  for (let i = 0; i < COLS * ROWS; i++) {
    const base = 0.05 + hash(i) * 0.07;
    const isFlash = i === flashIndex;
    const flash = isFlash
      ? interpolate(frame, [95, 108, 122, 140], [base, 0.9, 0.9, base], clamp)
      : base;
    tiles.push(
      <div
        key={i}
        style={{
          border: `1px solid ${theme.text3}`,
          borderRadius: 2,
          opacity: interpolate(frame, [0, 24], [0, flash], clamp),
          background: isFlash && frame > 95 && frame < 140 ? theme.accent : "transparent",
          transition: "none",
        }}
      />
    );
  }
  return (
    <AbsoluteFill
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${COLS}, 1fr)`,
        gridTemplateRows: `repeat(${ROWS}, 1fr)`,
        gap: 10,
        padding: 60,
      }}
    >
      {tiles}
    </AbsoluteFill>
  );
}

export function Scene1Problem({ durationInFrames }) {
  const frame = useCurrentFrame();
  return (
    <SceneShell durationInFrames={durationInFrames}>
      <CameraGrid frame={frame} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 22, padding: 40 }}>
          <MonoLabel delay={6}>Ahmedabad · Surat · Vadodara · Rajkot — live feeds</MonoLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <Headline delay={22} size={54}>EVERY CITY IS COVERED IN CAMERAS.</Headline>
            <Headline delay={118} size={54} color={theme.accent}>
              ALMOST NONE OF THEM ARE ACTUALLY WATCHING.
            </Headline>
          </div>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
