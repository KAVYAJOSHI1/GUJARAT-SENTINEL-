import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import FeedTile from "./FeedTile.jsx";

gsap.registerPlugin(ScrollTrigger);

// Abstract/representative tile codes — deliberately NOT real camera IDs.
// This section dramatizes "many disconnected feeds" as a concept; it does
// not claim SENTINEL currently operates this many cameras (the real count,
// 8, shows up honestly later in the product-reveal section).
const NOISE_TILES = Array.from({ length: 18 }, (_, i) => ({
  code: `CAM-${100 + i * 7}`,
  status: i % 9 === 0 ? "offline" : i % 5 === 0 ? "degraded" : "online",
}));

/** Act 1: the feed multiplies. No correlation, no memory between cameras —
 * just noise. This is the tension the rest of the page resolves. */
export default function ProblemSection() {
  const rootRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-problem-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });
      gsap.from(".hp-noise-tile", {
        opacity: 0, scale: 0.85, duration: 0.5, ease: "power2.out",
        stagger: { each: 0.035, from: "random" },
        scrollTrigger: { trigger: ".hp-noise-grid", start: "top 85%" },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="hp-section hp-problem">
      <div className="hp-ghost-word" aria-hidden="true">NOISE</div>
      <div className="hp-problem-heading">
        <div className="hp-eyebrow">THE PROBLEM</div>
        <h2 className="hp-h2">Thousands of feeds. No memory between them.</h2>
        <p className="hp-lede">
          A camera on every junction doesn't make a city watched — it makes a wall of
          disconnected screens. An operator can stare at one feed, or fifty, but nothing
          today tells them the same vehicle just passed camera four, and six, and eleven.
        </p>
      </div>
      <div className="hp-noise-grid">
        {NOISE_TILES.map((t) => (
          <FeedTile key={t.code} code={t.code} status={t.status} className="hp-noise-tile" />
        ))}
      </div>
    </section>
  );
}
