import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Headline, MonoLabel } from "../components/Text.jsx";
import { theme, REAL_DEMO } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

const STEPS = [
  { title: "ALERT", detail: REAL_DEMO.plate, color: theme.amber, start: 40 },
  { title: "INVESTIGATION", detail: "journey reconstructed", color: theme.accent, start: 100 },
  { title: "CASE", detail: REAL_DEMO.caseId, color: theme.accentLight, start: 160 },
  { title: "REPORT", detail: "evidence exported", color: theme.green, start: 220 },
];

function Chip({ step, frame }) {
  const { fps } = useVideoConfig();
  const local = frame - step.start;
  const s = spring({ frame: local, fps, config: { damping: 16, stiffness: 120, mass: 0.6 } });
  const opacity = interpolate(local, [0, 10], [0, 1], clamp);
  const y = interpolate(s, [0, 1], [18, 0]);
  return (
    <div
      style={{
        opacity,
        transform: `translateY(${y}px)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
        minWidth: 190,
      }}
    >
      <div
        style={{
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: step.color,
          boxShadow: `0 0 16px ${step.color}`,
        }}
      />
      <div style={{ fontFamily: theme.fontDisplay, fontSize: 30, color: theme.text, letterSpacing: 1 }}>{step.title}</div>
      <MonoLabel delay={0} size={12} color={theme.text2}>{step.detail}</MonoLabel>
    </div>
  );
}

function Connector({ from, to, frame }) {
  const progress = interpolate(frame, [from + 14, to - 4], [0, 1], clamp);
  return (
    <div style={{ flex: 1, height: 1.5, alignSelf: "center", background: theme.viridian, position: "relative", top: -34, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: theme.accent, transform: `scaleX(${progress})`, transformOrigin: "left" }} />
    </div>
  );
}

export function Scene5Workflow({ durationInFrames }) {
  const frame = useCurrentFrame();
  const headlineOpacity = interpolate(frame, [280, 300], [0, 1], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 60 }}>
        <MonoLabel delay={4} color={theme.text2}>from a match to a case file — automatically</MonoLabel>
        <div style={{ display: "flex", alignItems: "flex-start", width: 980 }}>
          {STEPS.map((step, i) => (
            <div key={step.title} style={{ display: "flex", alignItems: "flex-start", flex: i < STEPS.length - 1 ? 1 : "0 0 auto" }}>
              <Chip step={step} frame={frame} />
              {i < STEPS.length - 1 && <Connector from={step.start} to={STEPS[i + 1].start} frame={frame} />}
            </div>
          ))}
        </div>
        <div style={{ opacity: headlineOpacity }}>
          <Headline size={30} delay={0} color={theme.text2}>
            Every match becomes evidence a case can stand on.
          </Headline>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
