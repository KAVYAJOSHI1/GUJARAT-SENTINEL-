import { AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { MonoLabel } from "../components/Text.jsx";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

const TAGLINE = ["SEE THE EVENT.", "CONNECT THE EVIDENCE.", "UNDERSTAND THE JOURNEY."];

export function Scene8Close({ durationInFrames }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const eyebrowOpacity = interpolate(frame, [0, 14], [0, 1], clamp);
  const s = spring({ frame: frame - 18, fps, config: { damping: 14, stiffness: 100, mass: 0.6 } });
  const lockupOpacity = interpolate(frame - 18, [0, 14], [0, 1], clamp);
  const lockupScale = interpolate(s, [0, 1], [0.88, 1]);
  const finalFade = interpolate(frame, [durationInFrames - 26, durationInFrames], [1, 0], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames} fadeIn={10} fadeOutLen={0}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 30, opacity: finalFade }}>
        <div style={{ opacity: eyebrowOpacity }}>
          <MonoLabel delay={0} color={theme.accent}>See Sentinel in action</MonoLabel>
        </div>
        <div style={{ opacity: lockupOpacity, transform: `scale(${lockupScale})`, display: "flex", alignItems: "center", gap: 18 }}>
          <Img src={staticFile("logo.png")} style={{ width: 58, height: 58, objectFit: "contain" }} />
          <div style={{ fontFamily: theme.fontDisplay, fontSize: 64, color: theme.text, letterSpacing: 2 }}>SENTINEL</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, marginTop: 6 }}>
          {TAGLINE.map((line, i) => {
            const localOpacity = interpolate(frame - (60 + i * 16), [0, 12], [0, 1], clamp);
            return (
              <div key={line} style={{ opacity: localOpacity, fontFamily: theme.fontMono, fontSize: 14, letterSpacing: 3, color: theme.text2, textTransform: "uppercase" }}>
                {line}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
