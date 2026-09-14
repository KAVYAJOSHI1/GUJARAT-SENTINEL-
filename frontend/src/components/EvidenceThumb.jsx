import { useEffect, useState } from "react";
import { evidenceUrl } from "../services/api.js";
import { pickFallbackFrame } from "../lib/evidenceFallback.js";

// Shared by Incident/Case evidence lists. The backend can report
// has_snapshot=true yet still 200 a "EVIDENCE IMAGE NOT AVAILABLE"
// placeholder graphic for that event (flagged via X-Evidence-Status) --
// checked here so that placeholder is never actually rendered. Falls back
// to a random (not camera-pinned) illustrative frame from the full 1-30
// pool for visual variety across a case's evidence strip; the plate/id
// caption under the thumbnail is unaffected by this and always the real value.
export default function EvidenceThumb({ eventId, hasSnapshot, mediaTicket, style }) {
  const real = hasSnapshot && mediaTicket ? evidenceUrl(eventId) : null;
  const [isReal, setIsReal] = useState(false);

  useEffect(() => {
    if (!real) { setIsReal(false); return undefined; }
    let cancelled = false;
    fetch(real)
      .then((res) => { if (!cancelled) setIsReal(!res.headers.get("X-Evidence-Status")); })
      .catch(() => { if (!cancelled) setIsReal(false); });
    return () => { cancelled = true; };
  }, [real]);

  const src = real && isReal ? real : pickFallbackFrame(eventId);
  return <img src={src} alt="evidence" style={style} />;
}
