import { useCallback, useEffect, useState } from "react";
import { isAuthenticated, login, setUnauthorizedHandler } from "../services/api.js";

/**
 * Wraps the app: shows a minimal login form until a JWT is stored, then renders
 * children. A 401 from any API call clears the token and drops back here.
 *
 * Set VITE_ALLOW_ANON=true to bypass the gate for pure-mock demos.
 */
export default function LoginGate({ children }) {
  const allowAnon = String(import.meta.env.VITE_ALLOW_ANON || "") === "true";
  const [authed, setAuthed] = useState(isAuthenticated() || allowAnon);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false));
  }, []);

  const submit = useCallback(
    async (e) => {
      e.preventDefault();
      setError("");
      setBusy(true);
      try {
        await login(username.trim(), password);
        setAuthed(true);
      } catch (err) {
        setError(
          err?.response?.data?.detail?.message ||
            err?.response?.data?.detail ||
            "Login failed — check credentials or backend."
        );
      } finally {
        setBusy(false);
      }
    },
    [username, password]
  );

  if (authed) return children;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "var(--c-bg)",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          width: 320,
          background: "var(--c-surface)",
          border: "1px solid var(--c-border)",
          borderRadius: 10,
          padding: "28px 26px",
        }}
      >
        <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: 1, color: "var(--c-accent)" }}>
          SENTINEL
        </div>
        <div style={{ color: "var(--c-muted)", fontSize: 12, marginTop: 4, marginBottom: 20 }}>
          Command Center — sign in
        </div>

        <label style={{ display: "block", fontSize: 11, color: "var(--c-muted)", marginBottom: 4 }}>
          Username
        </label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          autoComplete="username"
          style={inputStyle}
        />

        <label style={{ display: "block", fontSize: 11, color: "var(--c-muted)", margin: "14px 0 4px" }}>
          Password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          style={inputStyle}
        />

        {error ? (
          <div style={{ color: "var(--c-red)", fontSize: 11, marginTop: 12 }}>{error}</div>
        ) : null}

        <button type="submit" disabled={busy} style={btnStyle}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  padding: "9px 10px",
  background: "var(--c-panel)",
  border: "1px solid var(--c-border)",
  borderRadius: 6,
  color: "var(--c-text)",
  fontSize: 13,
};

const btnStyle = {
  width: "100%",
  marginTop: 20,
  padding: "10px 0",
  background: "var(--c-accent)",
  color: "#0b0f14",
  border: "none",
  borderRadius: 6,
  fontWeight: 600,
  cursor: "pointer",
};
