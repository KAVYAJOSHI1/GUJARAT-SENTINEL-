import { createContext, useContext, useEffect, useState } from "react";

const MotionContext = createContext(false);

/** Whether the visitor asked the OS for reduced motion. Every scroll-linked
 * animation in the Home page reads this instead of assuming full motion is
 * safe — Lenis, ScrollTrigger scrub/pin, and the parallax layers all fall
 * back to plain static reveals when true. */
export function useReducedMotion() {
  return useContext(MotionContext);
}

export function MotionProvider({ children }) {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return <MotionContext.Provider value={reduced}>{children}</MotionContext.Provider>;
}
