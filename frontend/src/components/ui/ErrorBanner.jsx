import { AlertTriangle, RefreshCw } from "lucide-react";
import { C } from "../../theme.js";

// Top warning banner shown when the backend REST API is unreachable
// (README §15 — "Backend connection lost. Retrying...").
export default function ErrorBanner({ message, onRetry, retrying }) {
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        background: C.redGlow,
        border: `1px solid ${C.red}55`,
        color: C.text,
        borderRadius: 6,
        padding: "8px 14px",
        fontSize: 12,
        marginBottom: 14,
      }}
    >
      <AlertTriangle size={15} color={C.red} />
      <span style={{ flex: 1 }}>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={retrying}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            background: "transparent",
            border: `1px solid ${C.red}66`,
            color: C.text,
            borderRadius: 4,
            padding: "3px 10px",
            fontSize: 11,
            cursor: retrying ? "default" : "pointer",
          }}
        >
          <RefreshCw
            size={11}
            style={{ animation: retrying ? "pulseRing 1s linear infinite" : "none" }}
          />
          {retrying ? "Retrying…" : "Retry"}
        </button>
      )}
    </div>
  );
}
