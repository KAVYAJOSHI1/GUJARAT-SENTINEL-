import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { Backdrop } from "./Backdrop.jsx";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" };

// Every scene gets a consistent cross-fade in/out on top of the shared
// backdrop+grain, so cuts read as an edited film rather than hard slide-swaps.
export function SceneShell({ durationInFrames, fadeIn = 14, fadeOutLen = 18, vignette = true, children }) {
  const frame = useCurrentFrame();
  // Build breakpoints, then drop any that collide (interpolate() requires a
  // strictly increasing input range — happens when fadeOutLen is 0/small).
  const rawPoints = [0, fadeIn, Math.max(fadeIn, durationInFrames - fadeOutLen), durationInFrames];
  const rawValues = [0, 1, 1, 0];
  const points = [rawPoints[0]];
  const values = [rawValues[0]];
  for (let i = 1; i < rawPoints.length; i++) {
    if (rawPoints[i] > points[points.length - 1]) {
      points.push(rawPoints[i]);
      values.push(rawValues[i]);
    }
  }
  const opacity = points.length > 1 ? interpolate(frame, points, values, clamp) : 1;
  return (
    <AbsoluteFill style={{ opacity }}>
      <Backdrop vignette={vignette}>{children}</Backdrop>
    </AbsoluteFill>
  );
}

export const clampOpts = clamp;
