import { useEffect, useRef } from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import { Bell, Cable, Crosshair, ScanLine } from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

const STAGES = [
  {
    icon: Cable,
    title: "Stream Ingestion",
    body: "RTSP over TCP, WebRTC and HLS, with PTS timestamping and exponential backoff reconnects — built for erratic camera networks, not lab conditions.",
    image: "/home/live-monitoring.jpg",
  },
  {
    icon: ScanLine,
    title: "AI Detection & ANPR",
    body: "YOLOv8 vehicle detection feeds EasyOCR plate reads, with multi-frame consensus voting to reject misreads. A plate we can't confirm is reported UNKNOWN — never guessed.",
    image: "/home/watchlist.jpg",
  },
  {
    icon: Crosshair,
    title: "Cross-Camera Correlation",
    body: "ByteTrack + normalized plate matching stitches sightings from different cameras into one journey — the real Investigation Workspace, mid-trace.",
    image: "/home/workspace-full.jpg",
  },
  {
    icon: Bell,
    title: "Alert & Investigation",
    body: "A watchlist match fires a WebSocket alert to the command center in real time, with a direct path into an incident and case file.",
    image: "/home/alerts.jpg",
  },
];


/** Act 3: how it actually works, end to end — pinned so the visitor's
 * scroll speed controls the pace of the pipeline, not an autoplay timer. */
export default function HowItWorksSection() {
  const rootRef = useRef(null);
  const trackRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from(".hp-hiw-heading", {
        opacity: 0, y: 24, duration: 0.7, ease: "power2.out",
        scrollTrigger: { trigger: rootRef.current, start: "top 75%" },
      });

      const mm = gsap.matchMedia();

      mm.add("(min-width: 900px)", () => {
        const track = trackRef.current;
        const distance = track.scrollWidth - window.innerWidth;
        gsap.to(track, {
          x: -distance,
          ease: "none",
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top top",
            end: () => `+=${distance + window.innerHeight * 0.6}`,
            scrub: 0.7,
            pin: true,
          },
        });
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="hp-hiw">
      <div className="hp-hiw-heading">
        <div className="hp-eyebrow">HOW IT WORKS</div>
        <h2 className="hp-h2">One pipeline, four honest stages.</h2>
      </div>
      <div className="hp-hiw-track" ref={trackRef}>
        {STAGES.map((s, i) => (
          <div key={s.title} className="hp-hiw-panel">
            <div className="hp-hiw-num">{String(i + 1).padStart(2, "0")}</div>
            <s.icon size={22} color="var(--c-accent)" />
            <div className="hp-hiw-title">{s.title}</div>
            <p className="hp-hiw-body">{s.body}</p>
            {s.image && (
              <div className="hp-hiw-shot">
                <img src={s.image} alt={`${s.title} — real capture`} />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
