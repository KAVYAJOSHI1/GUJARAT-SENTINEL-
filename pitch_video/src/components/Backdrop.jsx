import { AbsoluteFill } from "remotion";
import { theme } from "../theme.js";

// The same layered-radial-gradient "ground" language as .hp-root's body
// background, minus the scroll-driven parallax (not applicable to a fixed video frame).
export function Backdrop({ children, vignette = true }) {
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse 120% 80% at 50% -10%, ${theme.bg3} 0%, ${theme.bg} 55%, ${theme.bg} 100%)`,
      }}
    >
      {children}
      {vignette && (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse 70% 70% at 50% 45%, rgba(0,0,0,0) 0%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)",
            pointerEvents: "none",
          }}
        />
      )}
      <Grain />
    </AbsoluteFill>
  );
}

// Cheap static film-grain texture via layered repeating gradients — reads as
// a premium filmic finish, costs nothing to render (no per-frame randomness).
function Grain() {
  return (
    <AbsoluteFill
      style={{
        opacity: 0.035,
        mixBlendMode: "overlay",
        pointerEvents: "none",
        backgroundImage:
          "repeating-linear-gradient(0deg, #fff 0px, transparent 1px, transparent 2px), repeating-linear-gradient(90deg, #fff 0px, transparent 1px, transparent 3px)",
      }}
    />
  );
}
