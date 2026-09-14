import { useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// Large display headline — the film's typographic backbone (Anton, the
// exact face .hp-root uses for its own H1/H2). Rises + fades in with a
// slight overshoot spring, like the real Hero's GSAP title-line reveal.
export function Headline({ children, delay = 0, size = 64, color, align = "center", style }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - delay;
  const s = spring({ frame: local, fps, config: { damping: 200, stiffness: 120, mass: 0.6 } });
  const opacity = interpolate(local, [0, 14], [0, 1], clamp);
  const y = interpolate(s, [0, 1], [28, 0]);
  return (
    <div
      style={{
        fontFamily: theme.fontDisplay,
        fontSize: size,
        lineHeight: 1.04,
        letterSpacing: 0.5,
        textAlign: align,
        color: color || theme.text,
        opacity,
        transform: `translateY(${y}px)`,
        textWrap: "balance",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// Small uppercase technical label — DM Mono, the same face the real HUD
// cards / eyebrow / stat labels use.
export function MonoLabel({ children, delay = 0, color, size = 13, style }) {
  const frame = useCurrentFrame();
  const local = frame - delay;
  const opacity = interpolate(local, [0, 10], [0, 1], clamp);
  const x = interpolate(local, [0, 10], [-10, 0], clamp);
  return (
    <div
      style={{
        fontFamily: theme.fontMono,
        fontSize: size,
        letterSpacing: 2.4,
        textTransform: "uppercase",
        color: color || theme.text2,
        opacity,
        transform: `translateX(${x}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// Body copy — Inter, matching .hp-hero-sub.
export function Body({ children, delay = 0, size = 22, color, align = "center", style }) {
  const frame = useCurrentFrame();
  const local = frame - delay;
  const opacity = interpolate(local, [0, 14], [0, 1], clamp);
  const y = interpolate(local, [0, 14], [12, 0], clamp);
  return (
    <div
      style={{
        fontFamily: theme.fontSans,
        fontWeight: 400,
        fontSize: size,
        lineHeight: 1.5,
        textAlign: align,
        color: color || theme.text2,
        opacity,
        transform: `translateY(${y}px)`,
        maxWidth: 760,
        textWrap: "balance",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function fadeOut(frame, sceneDurationInFrames, tail = 16) {
  return interpolate(frame, [sceneDurationInFrames - tail, sceneDurationInFrames], [1, 0], clamp);
}
