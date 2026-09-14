import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Body, MonoLabel } from "../components/Text.jsx";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

function Stat({ number, label, delay }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - delay;
  const s = spring({ frame: local, fps, config: { damping: 14, stiffness: 110, mass: 0.5 } });
  const opacity = interpolate(local, [0, 8], [0, 1], clamp);
  const scale = interpolate(s, [0, 1], [0.85, 1]);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, opacity, transform: `scale(${scale})` }}>
      <div style={{ fontFamily: theme.fontDisplay, fontSize: 96, color: theme.text, lineHeight: 1 }}>{number}</div>
      <MonoLabel delay={0} size={14} color={theme.text2}>{label}</MonoLabel>
    </div>
  );
}

export function Scene2ProblemDetail({ durationInFrames }) {
  const frame = useCurrentFrame();
  const rowOpacity = interpolate(frame, [0, 20], [0, 1], clamp);
  const synthesisOpacity = interpolate(frame, [190, 210], [0, 1], clamp);
  const rowFade = interpolate(frame, [190, 210], [1, 0.25], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 56 }}>
        <div style={{ display: "flex", gap: 90, opacity: rowOpacity * rowFade, transform: `scale(${interpolate(frame, [190, 230], [1, 0.9], clamp)})` }}>
          <Stat number="10" label="cameras passed" delay={10} />
          <div style={{ width: 1, background: theme.text3, opacity: 0.4 }} />
          <Stat number="10" label="minutes elapsed" delay={45} />
          <div style={{ width: 1, background: theme.text3, opacity: 0.4 }} />
          <Stat number="0" label="people watching" delay={80} />
        </div>
        <div style={{ opacity: synthesisOpacity, maxWidth: 820, padding: "0 40px" }}>
          <Body size={26} color={theme.text}>
            A wanted vehicle can pass ten cameras in ten minutes — and be seen
            by exactly <span style={{ color: theme.accent, fontWeight: 600 }}>zero</span> people.
          </Body>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
