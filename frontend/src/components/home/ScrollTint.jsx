import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { useReducedMotion } from "./MotionContext.jsx";

gsap.registerPlugin(ScrollTrigger);

// One tint per story beat — a subtle colour wash behind the section, not a
// flat background swap, so the grid texture and section content stay
// exactly as designed. This is the "each scroll phase has a different
// contrast" effect from the reference site, approximated as a fixed
// backdrop layer rather than its own multi-phase render pipeline.
const STOPS = [
  { selector: ".hp-hero", color: "rgba(94,207,184,0.10)" },
  { selector: ".hp-problem", color: "rgba(232,93,74,0.09)" },
  { selector: ".hp-insight", color: "rgba(94,207,184,0.14)" },
  { selector: ".hp-reveal", color: "rgba(245,240,232,0.05)" },
  { selector: ".hp-hiw", color: "rgba(232,160,69,0.08)" },
  { selector: ".hp-diff", color: "rgba(94,207,184,0.09)" },
  { selector: ".hp-impact", color: "rgba(94,207,184,0.16)" },
  { selector: ".hp-cta-section", color: "rgba(94,207,184,0.2)" },
];

/** A fixed backdrop wash whose colour crossfades as each story section
 * enters view — sits behind everything (z-index 0), never intercepts
 * clicks. Purely atmospheric. */
export default function ScrollTint() {
  const ref = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced || !ref.current) return undefined;
    const el = ref.current;
    const triggers = STOPS.map(({ selector, color }) => {
      const target = document.querySelector(selector);
      if (!target) return null;
      return ScrollTrigger.create({
        trigger: target,
        start: "top center",
        end: "bottom center",
        onEnter: () => gsap.to(el, { backgroundColor: color, duration: 0.8, ease: "power1.out" }),
        onEnterBack: () => gsap.to(el, { backgroundColor: color, duration: 0.8, ease: "power1.out" }),
      });
    });
    return () => triggers.forEach((t) => t?.kill());
  }, [reduced]);

  return <div ref={ref} className="hp-scroll-tint" aria-hidden="true" />;
}
