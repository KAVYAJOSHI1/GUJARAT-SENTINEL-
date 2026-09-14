import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/** Act 2: the product itself. Both images are real screenshots captured
 * from a locally-running SENTINEL instance (seeded with the repo's own
 * deterministic demo dataset) — not illustrations. The KPI values quoted
 * below are read directly off that capture, a snapshot in time rather than
 * a live re-fetch (this page renders before authentication). */
export default function ProductRevealSection() {
  const rootRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-reveal-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });
      gsap.utils.toArray(".hp-reveal-frame").forEach((el, i) => {
        gsap.from(el, {
          opacity: 0, y: 60, clipPath: "inset(8% 0 8% 0)", duration: 0.9, ease: "power2.out",
          delay: i * 0.1,
          scrollTrigger: { trigger: el, start: "top 82%" },
        });
      });
      gsap.from(".hp-kpi-chip", {
        opacity: 0, y: 14, duration: 0.5, stagger: 0.08, ease: "power2.out",
        scrollTrigger: { trigger: ".hp-kpi-row", start: "top 88%" },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="hp-section hp-reveal">
      <div className="hp-ghost-word" aria-hidden="true">LIVE</div>
      <div className="hp-reveal-heading">
        <div className="hp-eyebrow">THIS IS SENTINEL</div>
        <h2 className="hp-h2">Not a mockup. A running command center.</h2>
        <p className="hp-lede">
          Captured live from an actual SENTINEL deployment, seeded with the same
          deterministic demo scenario used to verify the platform end to end.
        </p>
      </div>

      <div className="hp-kpi-row">
        <div className="hp-kpi-chip"><span className="hp-kpi-val" style={{ color: "var(--c-red)" }}>4</span>Active Alerts</div>
        <div className="hp-kpi-chip"><span className="hp-kpi-val" style={{ color: "var(--c-green)" }}>7/8</span>Cameras Online</div>
        <div className="hp-kpi-chip"><span className="hp-kpi-val" style={{ color: "var(--c-violet)" }}>1</span>Open Case</div>
        <div className="hp-kpi-chip"><span className="hp-kpi-val" style={{ color: "var(--c-amber)" }}>1</span>Open Incident</div>
      </div>

      <div className="hp-browser-frame hp-reveal-frame">
        <div className="hp-browser-bar">
          <span /><span /><span />
          <span className="hp-browser-url">sentinel.gujarat.gov.in/command-center</span>
        </div>
        <img src="/home/command-center.jpg" alt="SENTINEL Command Center — real capture" className="hp-browser-img" />
      </div>

      <div className="hp-browser-frame hp-reveal-frame">
        <div className="hp-browser-bar">
          <span /><span /><span />
          <span className="hp-browser-url">sentinel.gujarat.gov.in/dashboard</span>
        </div>
        <img src="/home/dashboard-top.jpg" alt="SENTINEL Operations Dashboard — real capture" className="hp-browser-img" />
      </div>
    </section>
  );
}
