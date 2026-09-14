import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { ShieldCheck, Timer, Radio, TrendingDown } from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

// Every claim here is a documented, verifiable property of the actual system
// (see DEMO_RUNBOOK.md and the AI pipeline's own reporting behaviour) — not
// marketing language invented for this page.
const POINTS = [
  {
    icon: TrendingDown,
    title: "Zero hallucinated plates",
    body: "When a plate can't be confidently read — wide-area feeds, oblique angles, poor light — the pipeline reports UNKNOWN. It never guesses.",
  },
  {
    icon: Radio,
    title: "Built for erratic networks",
    body: "RTSP over TCP with exponential backoff reconnects (2s → 4s → 8s → 16s → 30s) — designed around real government camera links, not a lab feed.",
  },
  {
    icon: Timer,
    title: "Sub-second alert delivery",
    body: "A watchlist match reaches the command center over a live WebSocket connection — no page refresh, no polling delay.",
  },
  {
    icon: ShieldCheck,
    title: "Tested against real footage",
    body: "Validated on the hackathon's own government CCTV feeds, not synthetic samples — the same 'not a simulation' bar the brief sets.",
  },
];

export default function DifferentiationSection() {
  const rootRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-diff-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });
      gsap.from(".hp-diff-card", {
        opacity: 0, y: 40, duration: 0.6, ease: "power2.out", stagger: 0.1,
        scrollTrigger: { trigger: ".hp-diff-grid", start: "top 82%" },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="hp-section hp-diff">
      <div className="hp-ghost-word" aria-hidden="true">PROOF</div>
      <div className="hp-diff-heading">
        <div className="hp-eyebrow">WHY IT'S DIFFERENT</div>
        <h2 className="hp-h2">Production-grade, on purpose.</h2>
      </div>
      <div className="hp-diff-grid">
        {POINTS.map((p) => (
          <div key={p.title} className="hp-diff-card hp-bracket-panel">
            <p.icon size={19} color="var(--hp-accent)" />
            <div className="hp-diff-title">{p.title}</div>
            <div className="hp-diff-body">{p.body}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
