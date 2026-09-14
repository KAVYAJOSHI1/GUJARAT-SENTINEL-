import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// The 8 real seeded cameras, positioned around a center node purely for
// layout (angles are illustrative, not a geographic projection — this is a
// network diagram, not a map). Ghost nodes beyond them represent potential
// scale, not current deployment.
const REAL_NODES = 8;
const GHOST_NODES = 46;

function polar(cx, cy, r, deg) {
  const rad = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

export default function ImpactNetworkSection() {
  const rootRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-impact-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });

      const tl = gsap.timeline({
        scrollTrigger: { trigger: ".hp-network-wrap", start: "top 70%" },
      });
      tl.from(".hp-net-center", { scale: 0, opacity: 0, duration: 0.4, ease: "back.out(2)" })
        .from(".hp-net-real-line", { opacity: 0, duration: 0.35, stagger: 0.05, ease: "power1.out" }, "-=0.1")
        .from(".hp-net-real-node", { scale: 0, opacity: 0, duration: 0.35, stagger: 0.05, ease: "back.out(2)" }, "-=0.4")
        .from(".hp-net-ghost-line", { opacity: 0, duration: 0.02, stagger: 0.006 }, "-=0.1")
        .from(".hp-net-ghost-node", { scale: 0, opacity: 0, duration: 0.3, stagger: 0.006 }, "<")
        .from(".hp-impact-caption", { opacity: 0, y: 16, duration: 0.5 }, "-=0.3");
    }, rootRef);
    return () => ctx.revert();
  }, []);

  const cx = 300, cy = 300;
  const realNodes = Array.from({ length: REAL_NODES }, (_, i) => polar(cx, cy, 90, (360 / REAL_NODES) * i - 90));
  const ghostNodes = Array.from({ length: GHOST_NODES }, (_, i) => {
    const ring = 150 + (i % 3) * 55;
    const angle = (360 / GHOST_NODES) * i * 2.3;
    return polar(cx, cy, ring, angle);
  });

  return (
    <section ref={rootRef} className="hp-section hp-impact">
      <div className="hp-ghost-word" aria-hidden="true">SCALE</div>
      <div className="hp-impact-heading">
        <div className="hp-eyebrow">SCALE</div>
        <h2 className="hp-h2">Built for one city. Designed for a state.</h2>
      </div>

      <div className="hp-network-wrap">
        <svg viewBox="0 0 600 600" className="hp-network-svg" aria-hidden="true">
          {ghostNodes.map(([x, y], i) => (
            <line key={`gl${i}`} x1={cx} y1={cy} x2={x} y2={y} className="hp-net-ghost-line" />
          ))}
          {realNodes.map(([x, y], i) => (
            <line key={`rl${i}`} x1={cx} y1={cy} x2={x} y2={y} className="hp-net-real-line" />
          ))}
          {ghostNodes.map(([x, y], i) => (
            <circle key={`gn${i}`} cx={x} cy={y} r={2.6} className="hp-net-ghost-node" />
          ))}
          {realNodes.map(([x, y], i) => (
            <circle key={`rn${i}`} cx={x} cy={y} r={7} className="hp-net-real-node" />
          ))}
          <circle cx={cx} cy={cy} r={11} className="hp-net-center" />
        </svg>
        <div className="hp-net-label-center">AHMEDABAD</div>
      </div>

      <div className="hp-impact-caption">
        <p>
          <strong>Today:</strong> 8 cameras, one working correlation and alert pipeline, verified
          end to end. <strong>The brief:</strong> Gujarat Police's own hackathon frames the eventual
          scale at 80,000+ cameras statewide. SENTINEL is architected for that number — not
          claiming to run it yet.
        </p>
      </div>
    </section>
  );
}
