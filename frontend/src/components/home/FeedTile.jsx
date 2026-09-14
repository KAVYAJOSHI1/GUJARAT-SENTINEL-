import { C } from "../../theme.js";

const STATUS_COLOR = { online: C.green, degraded: C.amber, offline: C.red, alert: C.red };

/** A single stylized camera-feed tile — the recurring visual unit of the
 * problem/insight sections. Deliberately NOT a photo: no real footage is
 * wired in yet (see the Home-page asset checklist), so this renders the
 * same HUD chrome (REC dot, camera code, status colour) the real Live
 * Monitoring Wall uses, over a dark scan-line placeholder rather than an
 * invented photo. Swap `image` in once real CCTV stills land. */
export default function FeedTile({
  code,
  label,
  status = "online",
  image,
  highlighted = false,
  plate,
  confidence,
  className = "",
  style,
}) {
  const color = STATUS_COLOR[status] || C.muted;
  return (
    <div
      className={`hp-tile ${highlighted ? "hp-tile-highlighted" : ""} ${className}`}
      style={{ "--tile-color": color, ...style }}
    >
      <div className="hp-tile-frame">
        {image ? (
          <img src={image} alt="" className="hp-tile-img" />
        ) : (
          <div className="hp-tile-scan" />
        )}
        {highlighted && (
          <div className="hp-tile-box">
            {plate && <span className="hp-tile-plate">{plate}</span>}
            {confidence && <span className="hp-tile-conf">{confidence}</span>}
          </div>
        )}
      </div>
      <div className="hp-tile-bar">
        <span className="hp-tile-dot" />
        <span className="hp-tile-code">{code}</span>
        {label && <span className="hp-tile-label">{label}</span>}
      </div>
    </div>
  );
}
