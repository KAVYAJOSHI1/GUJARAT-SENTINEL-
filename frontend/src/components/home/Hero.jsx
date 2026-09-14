import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { ChevronDown } from "lucide-react";
import ThreeScene from "./ThreeScene.jsx";
import { useReducedMotion } from "./MotionContext.jsx";

gsap.registerPlugin(ScrollTrigger);

// Real seeded-scenario values (verified against the running app's own API —
// not invented) — presented here the way Orqis presents its own live agent
// telemetry in floating HUD cards.
const HUD = [
  { tag: "CAM-01 · PALDI CIRCLE", val: "WATCHLIST HIT", tone: "warm" },
  { tag: "ANPR CONFIDENCE", val: "93%", tone: "accent" },
  { tag: "CASE-2026-9001", val: "OPEN", tone: "plain" },
  { tag: "GJ18TC0450", val: "5 SIGHTINGS · 5 CAMERAS", tone: "plain" },
];

/** Act 0: a single, ordinary camera feed. Nothing intelligent about it
 * yet — that's the point. The 3D aperture is SENTINEL's vision made
 * literal: it tracks the cursor the way the product tracks a plate. */
export default function Hero({ onEnter }) {
  const rootRef = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
      tl.from(".hp-hero-eyebrow", { opacity: 0, y: 16, duration: 0.7 })
        .from(".hp-hero-title-line", { opacity: 0, y: 34, duration: 0.9, stagger: 0.08 }, "-=0.35")
        .from(".hp-hero-sub", { opacity: 0, y: 18, duration: 0.7 }, "-=0.45")
        .from(".hp-hero-cta-row > *", { opacity: 0, y: 14, duration: 0.6, stagger: 0.08 }, "-=0.4")
        .from(".hp-hero-stat", { opacity: 0, y: 10, duration: 0.5, stagger: 0.06 }, "-=0.3")
        .from(".hp-hud-card", { opacity: 0, x: 20, duration: 0.6, stagger: 0.09 }, "-=0.8")
        .from(".hp-hero-stage", { opacity: 0, scale: 0.92, duration: 1.1, ease: "power2.out" }, "-=1.1");

      // Real multi-layer parallax as the hero scrolls away — each layer
      // moves at a different rate (background slowest, foreground copy
      // fastest), which is what actually reads as "parallax" rather than
      // a single element fading. The 3D object recedes and dims slightly
      // but never shrinks to near-nothing, so it doesn't look like it's
      // breaking/dying mid-scroll.
      if (!reduced) {
        const parallax = gsap.timeline({
          scrollTrigger: { trigger: rootRef.current, start: "top top", end: "bottom top", scrub: 0.4 },
        });
        parallax
          .to(".hp-ghost-word", { yPercent: 30, ease: "none" }, 0)
          .to(".hp-hero-stage", { yPercent: -18, opacity: 0.35, ease: "none" }, 0)
          .to(".hp-hud-stack", { yPercent: -12, ease: "none" }, 0)
          .to(".hp-hero-copy", { yPercent: -6, ease: "none" }, 0);
      }
    }, rootRef);
    return () => ctx.revert();
  }, [reduced]);

  return (
    <section ref={rootRef} className="hp-hero">
      <div className="hp-ghost-word" aria-hidden="true">SENTINEL</div>

      <div className="hp-hero-stage">
        <ThreeScene className="hp-hero-canvas" />
        <div className="hp-hero-glow-floor" />
      </div>

      <div className="hp-hero-scroll-label">SCROLL THE STORY</div>
      <div className="hp-hud-stack">
        {HUD.map((h) => (
          <div key={h.tag} className="hp-hud-card hp-bracket-panel">
            <div className="hp-hud-card-title">({h.tag})</div>
            <div className="hp-hud-card-val">
              <em style={h.tone === "warm" ? { color: "var(--c-amber)" } : undefined}>{h.val}</em>
            </div>
          </div>
        ))}
      </div>

      <div className="hp-hero-copy">
        <div className="hp-hero-eyebrow">GUJARAT POLICE · INNOVATION HACKATHON 2026</div>
        <h1 className="hp-hero-title">
          <span className="hp-hero-title-line">EVERY CITY</span>
          <span className="hp-hero-title-line">HAS EYES.</span>
          <span className="hp-hero-title-line hp-hero-title-accent">SENTINEL MAKES THEM THINK.</span>
        </h1>
        <p className="hp-hero-sub">
          Real-time ANPR, cross-camera correlation and watchlist alerts —
          one command center for Gujarat's camera network.
        </p>
        <div className="hp-hero-cta-row">
          <button className="hp-hero-cta" onClick={onEnter}>
            Enter Command Center →
          </button>
          <span className="hp-hero-cta-hint">
            <ChevronDown size={13} /> scroll to see how
          </span>
        </div>
        <div className="hp-hero-stats">
          <div className="hp-hero-stat"><b>8</b>CAMERAS LIVE</div>
          <div className="hp-hero-stat"><b>93%</b>ANPR CONFIDENCE</div>
          <div className="hp-hero-stat"><b>&lt;1S</b>ALERT LATENCY</div>
          <div className="hp-hero-stat"><b>0</b>HALLUCINATED PLATES</div>
        </div>
      </div>
    </section>
  );
}
