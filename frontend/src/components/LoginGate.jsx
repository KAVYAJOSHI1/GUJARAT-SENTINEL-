import { useCallback, useEffect, useState } from "react";
import { isAuthenticated, login, setUnauthorizedHandler } from "../services/api.js";
import { ensureMediaTicket } from "../services/mediaTicket.js";
import LandingPage from "./LandingPage.jsx";

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

  // Warm the media-ticket cache whenever we're authenticated (covers the
  // "already had a stored JWT on load" path; the fresh-login path is warmed
  // inside login() itself).
  useEffect(() => {
    if (authed && !allowAnon) ensureMediaTicket().catch(() => {});
  }, [authed, allowAnon]);

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
    <LandingPage
      username={username}
      setUsername={setUsername}
      password={password}
      setPassword={setPassword}
      error={error}
      busy={busy}
      onSubmit={submit}
    />
  );
}
