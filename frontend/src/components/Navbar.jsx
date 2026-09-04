import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Bell, BellOff, MapPinned } from "lucide-react";
import { C, LOGO_URL } from "../theme.js";
import Pulse from "./Pulse.jsx";
import ConnectionIndicator from "./ui/ConnectionIndicator.jsx";
import { useToast } from "../context/ToastContext.jsx";

const TABS = [
  { to: "/", label: "Overview", end: true },
  { to: "/cameras", label: "Cameras" },
  { to: "/alerts", label: "Alerts" },
  { to: "/map", label: "Map" },
];

export default function Navbar({ wsStatus, unackCount = 0, critCount = 0 }) {
  const [time, setTime] = useState(new Date());
  const { muted, toggleMuted } = useToast();

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const tabStyle = ({ isActive }) => ({
    background: isActive ? C.accentGlow : "transparent",
    border: `1px solid ${isActive ? C.accent : "transparent"}`,
    color: isActive ? C.accent : C.muted,
    borderRadius: 4,
    padding: "4px 12px",
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 0.8,
    cursor: "pointer",
    whiteSpace: "nowrap",
  });

  return (
    <header
      style={{
        background: C.surface,
        borderBottom: `1px solid ${C.border}`,
        padding: "0 24px",
        minHeight: 52,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}>
        <img src={LOGO_URL} alt="Gujarat Police" style={{ width: 34, height: 34, objectFit: "contain" }} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: 0.3, color: C.text }}>
            SENTINEL
          </div>
          <div style={{ color: C.muted, fontSize: 9, letterSpacing: 2, textTransform: "uppercase" }}>
            Integrated Command &amp; Control
          </div>
        </div>
        {critCount > 0 && (
          <div
            style={{
              background: C.red,
              color: "#fff",
              borderRadius: 3,
              padding: "2px 10px",
              fontSize: 11,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              gap: 5,
              marginLeft: 4,
            }}
          >
            <Pulse color="#fff" /> {critCount} CRITICAL
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", padding: "8px 0" }}>
        <nav className="nav-tabs">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.end} style={tabStyle}>
              {t.label}
              {t.label === "Alerts" && unackCount > 0 ? ` (${unackCount})` : ""}
            </NavLink>
          ))}
          {/* Deep link into Vishakha's GIS / Investigation console
              (feature/vishakha-investigation). Route owned by her. */}
          <NavLink to="/investigation" style={tabStyle}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <MapPinned size={12} /> Investigation
            </span>
          </NavLink>
        </nav>

        <ConnectionIndicator status={wsStatus} />

        <button
          onClick={toggleMuted}
          title={muted ? "Alert sound off" : "Alert sound on"}
          style={{
            background: "transparent",
            border: `1px solid ${C.border}`,
            color: muted ? C.muted : C.accent,
            borderRadius: 4,
            padding: "4px 6px",
            display: "flex",
            cursor: "pointer",
          }}
        >
          {muted ? <BellOff size={13} /> : <Bell size={13} />}
        </button>

        <div className="header-meta-date" style={{ fontFamily: "monospace", color: C.muted, fontSize: 12 }}>
          {time.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}&nbsp;
          <span style={{ color: C.accent }}>
            {time.toLocaleTimeString("en-IN", { hour12: false })}
          </span>
        </div>

        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: C.panel,
            border: `1px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            color: C.muted,
          }}
        >
          IS
        </div>
      </div>
    </header>
  );
}
