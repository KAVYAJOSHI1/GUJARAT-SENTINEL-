import { forwardRef, useEffect } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/** The story's last beat and the real, functional sign-in form — unchanged
 * auth logic, passed straight through from LoginGate via LandingPage. */
const FinalCtaSection = forwardRef(function FinalCtaSection(
  { username, setUsername, password, setPassword, error, busy, onSubmit },
  ref
) {
  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-cta-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: ".hp-cta-section", start: "top 78%" },
      });
      gsap.from(".hp-cta-form", {
        opacity: 0, y: 34, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: ".hp-cta-section", start: "top 72%" },
      });
    });
    return () => ctx.revert();
  }, []);

  return (
    <section ref={ref} className="hp-cta-section">
      <div className="hp-ghost-word" aria-hidden="true">ENTER</div>
      <div className="hp-cta-heading">
        <div className="hp-eyebrow">READY</div>
        <h2 className="hp-h2">Step into the command center.</h2>
        <p className="hp-lede">Everything on this page runs live behind this login.</p>
      </div>

      <form onSubmit={onSubmit} className="hp-cta-form">
        <div className="ld-signin-brand">SENTINEL</div>
        <div className="ld-signin-sub">Command Center — sign in</div>

        <label className="ld-label">Username</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          className="ld-input"
        />

        <label className="ld-label" style={{ marginTop: 14 }}>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          className="ld-input"
        />

        {error ? <div className="ld-error">{error}</div> : null}

        <button type="submit" disabled={busy} className="ld-submit">
          {busy ? "Signing in…" : "Enter Command Center"}
        </button>
      </form>
    </section>
  );
});

export default FinalCtaSection;
