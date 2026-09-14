import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { SceneShell } from "../components/SceneShell.jsx";
import { theme } from "../theme.js";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// A faithful re-render of the real frontend/src/components/home/Hero.jsx —
// same copy, same tokens — pushed in cinematically rather than scraped as a
// static screenshot. No scrolling, no feature tour, per the brief.
export function Scene7Landing({ durationInFrames }) {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.09], clamp);
  const ghostX = interpolate(frame, [0, durationInFrames], [0, -18], clamp);
  const opacity = interpolate(frame, [0, 16], [0, 1], clamp);

  return (
    <SceneShell durationInFrames={durationInFrames} fadeIn={10} fadeOutLen={14}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `scale(${scale})`, opacity }}>
        <div
          style={{
            position: "absolute",
            fontFamily: theme.fontDisplay,
            fontSize: 240,
            color: theme.accent,
            opacity: 0.05,
            letterSpacing: 6,
            whiteSpace: "nowrap",
            transform: `translateX(${ghostX}px)`,
          }}
        >
          SENTINEL
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20, padding: 40 }}>
          <div style={{ fontFamily: theme.fontMono, fontSize: 12, letterSpacing: 3, textTransform: "uppercase", color: theme.text2 }}>
            Gujarat Police · Innovation Hackathon 2026
          </div>
          <div style={{ fontFamily: theme.fontDisplay, fontSize: 56, lineHeight: 1.08, textAlign: "center", color: theme.text }}>
            EVERY CITY HAS EYES.<br />
            <span style={{ color: theme.accent }}>SENTINEL MAKES THEM THINK.</span>
          </div>
          <div style={{ fontFamily: theme.fontSans, fontSize: 18, color: theme.text2, textAlign: "center", maxWidth: 620, lineHeight: 1.5 }}>
            Real-time ANPR, cross-camera correlation and watchlist alerts —
            one command center for Gujarat&rsquo;s camera network.
          </div>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
}
