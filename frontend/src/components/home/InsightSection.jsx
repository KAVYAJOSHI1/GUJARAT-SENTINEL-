import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { C } from "../../theme.js";
import { useReducedMotion } from "./MotionContext.jsx";

gsap.registerPlugin(ScrollTrigger);

// Real seeded journey data (verified against the running app's own API —
// GET /api/v1/vehicles/search?plate=GJ18TC0450 — not invented). This is the
// same demo scenario the actual Investigation Workspace resolves.
const STOPS = [
  { code: "CAM-01", label: "Paldi Circle", time: "13:47" },
  { code: "CAM-02", label: "Nehru Bridge West", time: "13:57" },
  { code: "CAM-04", label: "Income Tax Circle", time: "14:07" },
];
const PLATE = "GJ18TC0450";
const CONFIDENCE = "93%";
const TILE_W = 300;
const GAP = 40;

export default function InsightSection() {
  const rootRef = useRef(null);
  const boxRef = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-insight-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });

      const mm = gsap.matchMedia();

      // Wide viewports + full motion: pin the track and scrub the shared
      // highlight box across the three real camera tiles.
      mm.add("(min-width: 900px)", () => {
        if (reduced) return undefined;
        gsap.set(boxRef.current, { x: 0 });
        gsap.set(".hp-insight-cap-0", { opacity: 1 });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: ".hp-insight-track-wrap",
            start: "top 60%",
            end: "+=900",
            scrub: 0.7,
            pin: ".hp-insight-track-wrap",
            pinSpacing: true,
          },
        });

        STOPS.forEach((_, i) => {
          if (i === 0) return;
          tl.to(boxRef.current, { x: i * (TILE_W + GAP), duration: 1, ease: "power2.inOut" }, i - 1)
            .to(`.hp-insight-cap-${i - 1}`, { opacity: 0, duration: 0.3 }, i - 1)
            .to(`.hp-insight-cap-${i}`, { opacity: 1, duration: 0.3 }, i - 0.7)
            .to(`.hp-insight-tile-${i - 1}`, { borderColor: C.border, duration: 0.3 }, i - 1)
            .to(`.hp-insight-tile-${i}`, { borderColor: C.accent, duration: 0.3 }, i - 0.7);
        });
        return () => tl.scrollTrigger?.kill();
      });

      // Narrow viewports (or reduced motion): no pin, no shared box — each
      // tile just reveals with its own static plate/confidence badge
      // (rendered in CSS via .hp-insight-static-badge).
      mm.add("(max-width: 899px)", () => {
        gsap.from(".hp-insight-tile", {
          opacity: 0, y: 30, duration: 0.5, stagger: 0.12, ease: "power2.out",
          scrollTrigger: { trigger: ".hp-insight-track-wrap", start: "top 80%" },
        });
      });

      return () => mm.revert();
    }, rootRef);
    return () => ctx.revert();
  }, [reduced]);

  return (
    <section ref={rootRef} className="hp-section hp-insight">
      <div className="hp-ghost-word" aria-hidden="true">SIGNAL</div>
      <div className="hp-insight-heading">
        <div className="hp-eyebrow">OUR INSIGHT</div>
        <h2 className="hp-h2">The same vehicle. Five cameras. One nobody was watching together.</h2>
        <p className="hp-lede">
          A stolen vehicle doesn't announce itself on any single feed. It shows up as one
          plate read at a junction, then another, then another — invisible unless something
          is holding all of them in memory at once.
        </p>
      </div>

      <div className="hp-insight-track-wrap">
        <div className="hp-insight-track" style={{ "--tile-w": `${TILE_W}px`, "--gap": `${GAP}px` }}>
          {STOPS.map((s, i) => (
            <div key={s.code} className={`hp-insight-tile hp-insight-tile-${i}`}>
              <div className="hp-tile-scan hp-insight-scan">
                <span className="hp-insight-static-badge">
                  {PLATE} · {CONFIDENCE}
                </span>
              </div>
              <div className="hp-tile-bar">
                <span className="hp-tile-dot" />
                <span className="hp-tile-code">{s.code}</span>
                <span className="hp-tile-label">{s.label}</span>
                <span className="hp-insight-time">{s.time}</span>
              </div>
            </div>
          ))}
          <div ref={boxRef} className="hp-insight-box">
            <span className="hp-insight-plate">{PLATE}</span>
            <span className="hp-insight-conf">{CONFIDENCE}</span>
          </div>
        </div>
        <div className="hp-insight-captions">
          {STOPS.map((s, i) => (
            <div key={s.code} className={`hp-insight-cap hp-insight-cap-${i}`}>
              {i === 0 && "First read: a plate, a timestamp, a location."}
              {i === 1 && "Same plate, a different camera, ten minutes later."}
              {i === 2 && "Three sightings later: this is a journey, not three coincidences."}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
