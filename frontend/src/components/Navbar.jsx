import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Bell, BellOff, ChevronDown, Command } from "lucide-react";
import { C, LOGO_URL } from "../theme.js";
import { currentRole } from "../services/api.js";
import Pulse from "./Pulse.jsx";
import GlobalSearch from "./ops/GlobalSearch.jsx";
import ConnectionIndicator from "./ui/ConnectionIndicator.jsx";
import { useToast } from "../context/ToastContext.jsx";

// Phase 16B — grouped navigation IA. Every Phase 10-15 route stays
// reachable; they are just organised into 5 workspaces instead of a flat
// 17-tab strip.
const NAV = [
  {
    label: "COMMAND",
    items: [
      { to: "/", label: "Command Center", end: true },
      { to: "/live-monitoring", label: "Live Monitoring" },
      { to: "/alerts", label: "Alerts" },
      { to: "/dashboard", label: "Operations Dashboard" },
    ],
  },
  {
    label: "INVESTIGATE",
    items: [
      { to: "/search", label: "Search" },
      { to: "/workspace", label: "Vehicle Workspace" },
      { to: "/investigation", label: "GIS Investigation" },
      { to: "/incidents", label: "Incidents" },
      { to: "/cases", label: "Cases" },
      { to: "/graph", label: "Investigation Graph" },
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [
      { to: "/traffic", label: "Traffic" },
      { to: "/anomalies", label: "Anomalies" },
      { to: "/anpr-intelligence", label: "ANPR Intelligence" },
      { to: "/camera-intelligence", label: "Camera Intelligence" },
      { to: "/copilot", label: "AI Copilot" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { to: "/cameras", label: "Camera Network" },
      { to: "/cameras/manage", label: "Camera Management" },
      { to: "/my-work", label: "My Work" },
      { to: "/reports", label: "Reports" },
      { to: "/map", label: "GIS Map" },
    ],
  },
  {
    label: "ADMIN",
    items: [
      { to: "/watchlists", label: "Watchlists" },
      { to: "/system", label: "System" },
      { to: "/admin", label: "Audit Log", adminOnly: true },
    ],
  },
];

export default function Navbar({ wsStatus, unackCount = 0, critCount = 0, notifUnread = 0 }) {
  const [time, setTime] = useState(new Date());
  const [openGroup, setOpenGroup] = useState(null);
  const { muted, toggleMuted } = useToast();
  const { pathname } = useLocation();
  const isAdmin = currentRole() === "ADMIN";
  const wrapRef = useRef(null);

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { setOpenGroup(null); }, [pathname]);
  useEffect(() => {
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpenGroup(null); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const groupActive = (g) =>
    g.items.some((i) => (i.to === "/" ? pathname === "/" : pathname.startsWith(i.to)));

  return (
    <header style={{
      background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "0 20px",
      minHeight: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: 14, flexWrap: "wrap", position: "sticky", top: 0, zIndex: 200,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}>
        <img src={LOGO_URL} alt="Gujarat Police" style={{ width: 32, height: 32, objectFit: "contain" }} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: 0.3, color: C.text }}>SENTINEL</div>
          <div style={{ color: C.muted, fontSize: 9, letterSpacing: 2, textTransform: "uppercase" }}>
            Integrated Command &amp; Control
          </div>
        </div>
        {critCount > 0 && (
          <div style={{ background: C.red, color: "#fff", borderRadius: 3, padding: "2px 10px", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", gap: 5, marginLeft: 4 }}>
            <Pulse color="#fff" /> {critCount} CRITICAL
          </div>
        )}
      </div>

      <nav ref={wrapRef} className="nav-tabs" style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", padding: "8px 0" }}>
        {NAV.map((g) => {
          const items = g.items.filter((i) => !i.adminOnly || isAdmin);
          if (!items.length) return null;
          const active = groupActive(g);
          const isOpen = openGroup === g.label;
          return (
            <div key={g.label} style={{ position: "relative" }}>
              <button onClick={() => setOpenGroup(isOpen ? null : g.label)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  background: isOpen || active ? C.accentGlow : "transparent",
                  border: `1px solid ${isOpen || active ? C.accent : "transparent"}`,
                  color: isOpen || active ? C.accent : C.muted,
                  borderRadius: 4, padding: "5px 10px", fontSize: 10.5, fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: 0.8, cursor: "pointer", whiteSpace: "nowrap",
                }}>
                {g.label} <ChevronDown size={11} />
              </button>
              {isOpen && (
                <div style={{
                  position: "absolute", top: "calc(100% + 5px)", left: 0, minWidth: 190,
                  background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6,
                  zIndex: 250, boxShadow: "0 10px 30px rgba(0,0,0,0.45)", overflow: "hidden",
                }}>
                  {items.map((i) => (
                    <NavLink key={i.to} to={i.to} end={i.end} onClick={() => setOpenGroup(null)}
                      style={({ isActive }) => ({
                        display: "block", padding: "8px 12px", fontSize: 11.5,
                        color: isActive ? C.accent : C.text, textDecoration: "none",
                        background: isActive ? C.accentGlow : "transparent",
                        borderLeft: `2px solid ${isActive ? C.accent : "transparent"}`,
                      })}>
                      {i.label}
                      {i.label === "Alerts" && unackCount > 0 ? ` (${unackCount})` : ""}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "8px 0" }}>
        <button onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))}
          title="Command palette (Ctrl+K)"
          style={{ display: "flex", alignItems: "center", gap: 5, background: C.panel, border: `1px solid ${C.border}`, color: C.muted, borderRadius: 4, padding: "4px 9px", fontSize: 10, cursor: "pointer" }}>
          <Command size={11} /> <span style={{ fontFamily: "monospace" }}>K</span>
        </button>
        <GlobalSearch />

        <NavLink to="/system" title="Notification center" style={({ isActive }) => ({ position: "relative", display: "flex", color: isActive ? C.accent : C.muted, textDecoration: "none" })}>
          <Bell size={15} />
          {notifUnread > 0 && (
            <span style={{ position: "absolute", top: -6, right: -8, background: C.red, color: "#fff", borderRadius: 8, fontSize: 9, fontWeight: 700, padding: "0 4px", minWidth: 14, textAlign: "center", lineHeight: "14px" }}>
              {notifUnread > 99 ? "99+" : notifUnread}
            </span>
          )}
        </NavLink>

        <ConnectionIndicator status={wsStatus} />

        <button onClick={toggleMuted} title={muted ? "Alert sound off" : "Alert sound on"}
          style={{ background: "transparent", border: `1px solid ${C.border}`, color: muted ? C.muted : C.accent, borderRadius: 4, padding: "4px 6px", display: "flex", cursor: "pointer" }}>
          {muted ? <BellOff size={13} /> : <Bell size={13} />}
        </button>

        <div className="header-meta-date" style={{ fontFamily: "monospace", color: C.muted, fontSize: 12 }}>
          {time.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}&nbsp;
          <span style={{ color: C.accent }}>{time.toLocaleTimeString("en-IN", { hour12: false })}</span>
        </div>
      </div>
    </header>
  );
}
