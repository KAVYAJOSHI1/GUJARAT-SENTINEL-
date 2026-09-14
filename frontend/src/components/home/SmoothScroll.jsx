import { useEffect, useRef } from "react";
import Lenis from "lenis";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { useReducedMotion } from "./MotionContext.jsx";

gsap.registerPlugin(ScrollTrigger);

/** Drives the whole Home page's scroll feel. Lenis owns the actual scroll
 * physics; every GSAP ScrollTrigger elsewhere on the page reads from the
 * SAME scroll position via the `lenis.on("scroll", ScrollTrigger.update)`
 * wire below, so pinned/scrubbed sections stay perfectly in sync with the
 * smoothed scroll instead of the raw wheel delta.
 *
 * Reduced-motion visitors get native browser scrolling instead — Lenis
 * itself is the "motion" here, not a section-level effect, so it's the one
 * thing this file is responsible for skipping. */
export default function SmoothScroll({ children }) {
  const reduced = useReducedMotion();
  const rootRef = useRef(null);

  useEffect(() => {
    if (reduced) return undefined;

    const lenis = new Lenis({
      duration: 1.05,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      smoothWheel: true,
    });

    lenis.on("scroll", ScrollTrigger.update);

    const tick = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  }, [reduced]);

  useEffect(() => {
    // Whenever content height changes (images loading, fonts swapping in)
    // ScrollTrigger's cached measurements go stale — refresh on load.
    const onLoad = () => ScrollTrigger.refresh();
    window.addEventListener("load", onLoad);
    return () => window.removeEventListener("load", onLoad);
  }, []);

  return <div ref={rootRef}>{children}</div>;
}
