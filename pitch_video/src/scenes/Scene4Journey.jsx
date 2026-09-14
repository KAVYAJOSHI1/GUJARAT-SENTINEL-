import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { Headline, MonoLabel } from "../components/Text.jsx";
import { theme, REAL_DEMO } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };
const VB_W = 1000;
const VB_H = 560;

// Real seeded camera codes + real Ahmedabad neighbourhood names from
// scripts/seed_ai_demo.py — nothing here is an invented location.
const NODES = {
  "CAM-01": { x: 120, y: 410, active: true, order: 0 },
  "CAM-02": { x: 300, y: 220, active: true, order: 1 },
  "CAM-03": { x: 430, y: 440, active: false },
  "CAM-04": { x: 505, y: 175, active: true, order: 2 },
  "CAM-05": { x: 615, y: 400, active: false },
  "CAM-06": { x: 705, y: 225, active: true, order: 3 },
  "CAM-07": { x: 800, y: 430, active: false },
  "CAM-08": { x: 900, y: 300, active: true, order: 4 },
};
const HOP_FRAMES = [30, 100, 170, 240, 310]; // activation frame for order 0..4
const pct = (v, span) => `${(v / span) * 100}%`;

function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function RouteLine({ from, to, drawStart, drawEnd, frame }) {
  const len = dist(from, to);
  const progress = interpolate(frame, [drawStart, drawEnd], [0, 1], clamp);
  return (
    <line
      x1={from.x} y1={from.y} x2={to.x} y2={to.y}
      stroke={theme.accent}
      strokeWidth={3}
      strokeLinecap="round"
      strokeDasharray={len}
      strokeDashoffset={len * (1 - progress)}
      opacity={0.9}
    />
  );
}

function DimGrid() {
  // faint static connective tissue between inactive nodes — reads as "a real
  // network", not just 5 isolated dots. Purely decorative, never claimed as data.
  const pairs = [
    ["CAM-01", "CAM-03"], ["CAM-03", "CAM-05"], ["CAM-05", "CAM-07"],
    ["CAM-02", "CAM-03"], ["CAM-04", "CAM-05"], ["CAM-06", "CAM-07"], ["CAM-07", "CAM-08"],
  ];
  return pairs.map(([a, b], i) => (
    <line key={i} x1={NODES[a].x} y1={NODES[a].y} x2={NODES[b].x} y2={NODES[b].y} stroke={theme.viridian} strokeWidth={1} opacity={0.5} />
  ));
}

function NodeDot({ code, frame }) {
  const n = NODES[code];
  const { fps } = useVideoConfig();
  if (!n.active) {
    return <circle cx={n.x} cy={n.y} r={5} fill={theme.text3} opacity={0.35} />;
  }
  const activateFrame = HOP_FRAMES[n.order];
  const local = frame - activateFrame;
  const s = spring({ frame: local, fps, config: { damping: 10, stiffness: 140, mass: 0.5 } });
  const r = interpolate(s, [0, 1], [3, 9], clamp);
  const ringR = interpolate(local, [0, 30], [9, 22], clamp);
  const ringOpacity = interpolate(local, [0, 30], [0.55, 0], clamp);
  const glow = interpolate(local, [0, 8], [0, 1], clamp);
  return (
    <g opacity={interpolate(local, [-2, 4], [0, 1], clamp)}>
      <circle cx={n.x} cy={n.y} r={ringR} fill="none" stroke={theme.accent} strokeWidth={1.5} opacity={ringOpacity} />
      <circle cx={n.x} cy={n.y} r={r} fill={theme.accent} style={{ filter: `drop-shadow(0 0 ${6 * glow}px ${theme.accent})` }} />
    </g>
  );
}

function NodeLabel({ code, frame }) {
  const n = NODES[code];
  if (!n.active) return null;
  const activateFrame = HOP_FRAMES[n.order];
  const opacity = interpolate(frame, [activateFrame + 4, activateFrame + 18], [0, 1], clamp);
  const flip = n.y < 260; // put label below node if node sits near the top
  return (
    <div
      style={{
        position: "absolute",
        left: pct(n.x, VB_W),
        top: pct(n.y, VB_H),
        transform: `translate(-50%, ${flip ? "14px" : "-30px"})`,
        opacity,
        textAlign: "center",
        whiteSpace: "nowrap",
      }}
    >
      <MonoLabel delay={0} size={11} color={theme.text}>
        {code} · {REAL_DEMO.journeyLabels[code]}
      </MonoLabel>
    </div>
  );
}

export function Scene4Journey({ durationInFrames }) {
  const frame = useCurrentFrame();
  const order = ["CAM-01", "CAM-02", "CAM-04", "CAM-06", "CAM-08"];

  const mapDim = interpolate(
    frame,
    [340, 350, 420, 430, 490],
    [1, 1, 0.22, 0.22, 0.55],
    clamp
  );
  const line1Opacity = interpolate(frame, [350, 366, 414, 430], [0, 1, 1, 0], clamp);
  const line2Opacity = interpolate(frame, [430, 446, 484], [0, 1, 1], clamp);
  // triad
  const t1 = interpolate(frame, [490, 502], [0, 1], clamp);
  const t2 = interpolate(frame, [504, 516], [0, 1], clamp);
  const t3 = interpolate(frame, [518, 530], [0, 1], clamp);
  const plateOpacity = interpolate(frame, [528, 538], [0, 1], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-start", paddingTop: 44 }}>
        <MonoLabel delay={4} color={theme.text2}>Gujarat · camera network — actual seeded route</MonoLabel>
      </AbsoluteFill>

      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", opacity: mapDim }}>
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} width="86%" style={{ overflow: "visible" }}>
          <DimGrid />
          <RouteLine from={NODES["CAM-01"]} to={NODES["CAM-02"]} drawStart={30} drawEnd={100} frame={frame} />
          <RouteLine from={NODES["CAM-02"]} to={NODES["CAM-04"]} drawStart={100} drawEnd={170} frame={frame} />
          <RouteLine from={NODES["CAM-04"]} to={NODES["CAM-06"]} drawStart={170} drawEnd={240} frame={frame} />
          <RouteLine from={NODES["CAM-06"]} to={NODES["CAM-08"]} drawStart={240} drawEnd={310} frame={frame} />
          {Object.keys(NODES).map((c) => <NodeDot key={c} code={c} frame={frame} />)}
        </svg>
        {order.map((c) => <NodeLabel key={c} code={c} frame={frame} />)}
      </AbsoluteFill>

      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        <div style={{ opacity: line1Opacity, position: "absolute" }}>
          <Headline size={50} delay={0}>ONE CAMERA SEES A CAR.</Headline>
        </div>
        <div style={{ opacity: line2Opacity, position: "absolute" }}>
          <Headline size={50} delay={0} color={theme.accent}>SENTINEL SEES WHERE IT&rsquo;S BEEN.</Headline>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: 70 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <div style={{ opacity: t1, fontFamily: theme.fontDisplay, fontSize: 34, color: theme.text }}>ONE VEHICLE.</div>
          <div style={{ opacity: t2, fontFamily: theme.fontDisplay, fontSize: 34, color: theme.text }}>MULTIPLE CAMERAS.</div>
          <div style={{ opacity: t3, fontFamily: theme.fontDisplay, fontSize: 34, color: theme.accent }}>ONE JOURNEY.</div>
          <div style={{ opacity: plateOpacity, marginTop: 10 }}>
            <MonoLabel delay={0} size={13} color={theme.text2}>{REAL_DEMO.plate} · 5 sightings · 5 cameras</MonoLabel>
          </div>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
