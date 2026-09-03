import { C } from "../theme.js";

// Animated pulsing dot used for live / critical indicators.
export default function Pulse({ color = C.red, size = 8 }) {
  return (
    <span style={{ position: "relative", display: "inline-block", width: size, height: size }}>
      <span
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          background: color,
          animation: "pulseRing 1.4s ease-out infinite",
          opacity: 0.6,
        }}
      />
      <span style={{ position: "absolute", inset: 1, borderRadius: "50%", background: color }} />
    </span>
  );
}
