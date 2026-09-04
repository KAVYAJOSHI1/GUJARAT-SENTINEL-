import { useState, useEffect, useRef } from "react";

// ─── Simulated Real-time Data ─────────────────────────────────────────────────
const CAMERAS = [
  { id: "CAM-001", name: "Sardar Bridge", zone: "Zone A", lat: 23.022, lng: 72.571, status: "active" },
  { id: "CAM-002", name: "Manek Chowk", zone: "Zone A", lat: 23.025, lng: 72.587, status: "active" },
  { id: "CAM-003", name: "Kalupur Junction", zone: "Zone B", lat: 23.035, lng: 72.605, status: "alert" },
  { id: "CAM-004", name: "Sola Highway", zone: "Zone C", lat: 23.071, lng: 72.529, status: "active" },
  { id: "CAM-005", name: "Naranpura Gate", zone: "Zone B", lat: 23.054, lng: 72.553, status: "offline" },
  { id: "CAM-006", name: "GIFT City Entry", zone: "Zone D", lat: 23.157, lng: 72.683, status: "active" },
];

const INITIAL_ALERTS = [
  { id: 1, type: "ANPR_MATCH", cam: "CAM-003", vehicle: "GJ-01-AB-1234", severity: "critical", msg: "Watchlist vehicle detected — stolen vehicle", time: "14:32:01", ack: false },
  { id: 2, type: "CROWD_ANOMALY", cam: "CAM-002", vehicle: null, severity: "high", msg: "Abnormal crowd density detected", time: "14:30:48", ack: false },
  { id: 3, type: "WRONG_WAY", cam: "CAM-001", vehicle: "GJ-05-CD-5678", severity: "medium", msg: "Wrong-way vehicle on Sardar Bridge", time: "14:28:15", ack: true },
  { id: 4, type: "ANPR_MATCH", cam: "CAM-004", vehicle: "GJ-18-XY-9900", severity: "high", msg: "Suspect vehicle — outstanding warrant", time: "14:25:00", ack: false },
];

const TRACKED_VEHICLES = [
  { plate: "GJ-01-AB-1234", make: "Maruti Swift", color: "Red", lastSeen: "CAM-003", time: "14:32:01", flag: "STOLEN", crossings: 3 },
  { plate: "GJ-18-XY-9900", make: "Toyota Innova", color: "White", lastSeen: "CAM-004", time: "14:25:00", flag: "WARRANT", crossings: 1 },
  { plate: "GJ-05-CD-5678", make: "Tata Nexon", color: "Blue", lastSeen: "CAM-001", time: "14:28:15", flag: "TRAFFIC", crossings: 5 },
];

// ─── Color tokens (dark, corporate) ───────────────────────────────────────────
const C = {
  bg: "#12161C",
  surface: "#181D25",
  panel: "#1F2530",
  border: "#2C333F",
  accent: "#4F9CD9",
  accentGlow: "rgba(79,156,217,0.12)",
  red: "#E0574C",
  redGlow: "rgba(224,87,76,0.12)",
  amber: "#D9A441",
  amberGlow: "rgba(217,164,65,0.12)",
  green: "#3FB37F",
  greenGlow: "rgba(63,179,127,0.12)",
  text: "#E5E9EE",
  muted: "#8993A1",
  dim: "#3A4250",
  // used only inside the simulated video-feed panels, which stay near-black regardless of theme
  feedText: "#CFE0EE",
  feedMuted: "#8FA6BC",
};

const LOGO_URL = "https://sentinel.gujarat.gov.in/public/logos/gujarat%20police%20logo.png";

// ─── Sub-components ───────────────────────────────────────────────────────────

function SeverityBadge({ s }) {
  const map = { critical: [C.red, "#2E1917"], high: [C.amber, "#2E2415"], medium: ["#9B8CEE", "#221E33"], low: [C.muted, "#20242B"] };
  const [fg, bg] = map[s] || [C.muted, C.surface];
  return (
    <span style={{ background: bg, color: fg, border: `1px solid ${fg}33`, borderRadius: 3, padding: "1px 7px", fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>
      {s}
    </span>
  );
}

function Pulse({ color = C.red }) {
  return (
    <span style={{ position: "relative", display: "inline-block", width: 8, height: 8 }}>
      <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: color, animation: "pulseRing 1.4s ease-out infinite", opacity: 0.6 }} />
      <span style={{ position: "absolute", inset: 1, borderRadius: "50%", background: color }} />
    </span>
  );
}

function StatCard({ label, value, sub, color = C.accent, pulse }) {
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "14px 18px", flex: 1, minWidth: 110 }}>
      <div style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 6 }}>{label}</div>
      <div style={{ color, fontSize: 28, fontWeight: 700, fontFamily: "'Space Mono', monospace", display: "flex", alignItems: "center", gap: 8 }}>
        {pulse && <Pulse color={color} />} {value}
      </div>
      {sub && <div style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function CameraCard({ cam, selected, onClick }) {
  const statusColor = { active: C.green, alert: C.red, offline: C.muted }[cam.status];
  const isAlert = cam.status === "alert";
  return (
    <div
      onClick={() => onClick(cam)}
      style={{
        background: selected ? C.accentGlow : C.panel,
        border: `1px solid ${selected ? C.accent : isAlert ? C.red : C.border}`,
        borderRadius: 6,
        padding: "10px 12px",
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ color: C.accent, fontSize: 11, fontFamily: "monospace", fontWeight: 700 }}>{cam.id}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {isAlert && <Pulse color={C.red} />}
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor, display: "inline-block" }} />
        </span>
      </div>
      {/* Simulated feed placeholder */}
      <div style={{ background: "#000", borderRadius: 4, height: 60, marginBottom: 8, position: "relative", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {cam.status === "offline"
          ? <span style={{ color: C.feedMuted, fontSize: 11 }}>NO SIGNAL</span>
          : <div style={{ position: "absolute", inset: 0, background: `linear-gradient(135deg, #071420 60%, ${isAlert ? "#200808" : "#081828"})` }}>
              <div style={{ position: "absolute", bottom: 4, left: 6, color: C.feedMuted, fontSize: 9, fontFamily: "monospace" }}>LIVE ●  {new Date().toLocaleTimeString()}</div>
              {isAlert && <div style={{ position: "absolute", top: 4, right: 6, color: C.red, fontSize: 9, fontWeight: 700, fontFamily: "monospace" }}>⚠ ALERT</div>}
            </div>}
      </div>
      <div style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{cam.name}</div>
      <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{cam.zone} · {cam.status.toUpperCase()}</div>
    </div>
  );
}

function AlertRow({ alert, onAck }) {
  const borderCol = { critical: C.red, high: C.amber, medium: "#9B8CEE" }[alert.severity] || C.muted;
  return (
    <div style={{
      display: "flex", gap: 12, alignItems: "flex-start",
      padding: "10px 14px", borderLeft: `3px solid ${alert.ack ? C.dim : borderCol}`,
      background: alert.ack ? "transparent" : `${borderCol}08`,
      opacity: alert.ack ? 0.55 : 1, marginBottom: 4, borderRadius: "0 4px 4px 0",
      transition: "all 0.2s",
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3 }}>
          <SeverityBadge s={alert.severity} />
          <span style={{ color: C.muted, fontSize: 10, fontFamily: "monospace" }}>{alert.type}</span>
          <span style={{ color: C.accent, fontSize: 10, fontFamily: "monospace" }}>{alert.cam}</span>
        </div>
        <div style={{ color: C.text, fontSize: 12 }}>{alert.msg}</div>
        {alert.vehicle && <div style={{ color: C.amber, fontSize: 11, fontFamily: "monospace", marginTop: 2 }}>🚘 {alert.vehicle}</div>}
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ color: C.muted, fontSize: 10, fontFamily: "monospace", marginBottom: 6 }}>{alert.time}</div>
        {!alert.ack && (
          <button onClick={() => onAck(alert.id)} style={{ background: "transparent", border: `1px solid ${C.dim}`, color: C.muted, borderRadius: 3, padding: "2px 8px", fontSize: 10, cursor: "pointer" }}>
            ACK
          </button>
        )}
      </div>
    </div>
  );
}

function VehicleRow({ v }) {
  const flagColor = { STOLEN: C.red, WARRANT: C.amber, TRAFFIC: "#9B8CEE" }[v.flag] || C.muted;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1.4fr 0.8fr 1.2fr 1fr 0.7fr 0.8fr", gap: 8, padding: "8px 12px", borderBottom: `1px solid ${C.border}`, fontSize: 11, alignItems: "center" }}>
      <span style={{ color: C.accent, fontFamily: "monospace", fontWeight: 700 }}>{v.plate}</span>
      <span style={{ color: C.text }}>{v.make}</span>
      <span style={{ color: C.muted }}>{v.color}</span>
      <span style={{ color: C.muted, fontFamily: "monospace" }}>{v.lastSeen}</span>
      <span style={{ color: C.muted, fontFamily: "monospace" }}>{v.time}</span>
      <span style={{ color: flagColor, fontWeight: 700 }}>{v.flag}</span>
      <span style={{ color: C.muted }}>{v.crossings}x</span>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function GujaratSentinelDashboard() {
  const [alerts, setAlerts] = useState(INITIAL_ALERTS);
  const [selectedCam, setSelectedCam] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [time, setTime] = useState(new Date());
  const [searchPlate, setSearchPlate] = useState("");

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Simulate new alerts every ~15s
  useEffect(() => {
    const t = setInterval(() => {
      const newAlert = {
        id: Date.now(),
        type: "SPEED_VIOLATION",
        cam: `CAM-00${Math.ceil(Math.random() * 6)}`,
        vehicle: `GJ-${Math.floor(Math.random() * 30).toString().padStart(2,"0")}-ZZ-${Math.floor(Math.random()*9000+1000)}`,
        severity: ["low", "medium"][Math.floor(Math.random() * 2)],
        msg: "Speed limit exceeded — 78 km/h in 50 zone",
        time: new Date().toLocaleTimeString("en-IN", { hour12: false }),
        ack: false,
      };
      setAlerts(prev => [newAlert, ...prev].slice(0, 30));
    }, 15000);
    return () => clearInterval(t);
  }, []);

  const ackAlert = (id) => setAlerts(prev => prev.map(a => a.id === id ? { ...a, ack: true } : a));

  const unackCount = alerts.filter(a => !a.ack).length;
  const critCount = alerts.filter(a => !a.ack && a.severity === "critical").length;
  const activeCams = CAMERAS.filter(c => c.status === "active").length;
  const alertCams = CAMERAS.filter(c => c.status === "alert").length;

  const filteredVehicles = TRACKED_VEHICLES.filter(v =>
    searchPlate === "" || v.plate.toLowerCase().includes(searchPlate.toLowerCase())
  );

  const tabs = ["overview", "cameras", "vehicles", "alerts"];

  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'Inter', -apple-system, sans-serif", fontSize: 13 }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@400;500;600;700&display=swap');
        @keyframes pulseRing {
          0% { transform: scale(1); opacity: 0.8; }
          100% { transform: scale(2.8); opacity: 0; }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; } 
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.dim}; border-radius: 2px; }
        button:hover { opacity: 0.85; }
      `}</style>

      {/* ── Header ── */}
      <header style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "0 24px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src={LOGO_URL} alt="Gujarat Police" style={{ width: 34, height: 34, objectFit: "contain" }} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: 0.3, color: C.text }}>Gujarat Police</div>
            <div style={{ color: C.muted, fontSize: 9, letterSpacing: 2, textTransform: "uppercase" }}>Integrated Command & Control</div>
          </div>
          {critCount > 0 && (
            <div style={{ background: C.red, color: "#fff", borderRadius: 3, padding: "2px 10px", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", gap: 5, marginLeft: 8 }}>
              <Pulse color="#fff" /> {critCount} CRITICAL
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ display: "flex", gap: 4 }}>
            {tabs.map(t => (
              <button key={t} onClick={() => setActiveTab(t)} style={{
                background: activeTab === t ? C.accentGlow : "transparent",
                border: `1px solid ${activeTab === t ? C.accent : "transparent"}`,
                color: activeTab === t ? C.accent : C.muted,
                borderRadius: 4, padding: "4px 12px", fontSize: 11, fontWeight: 600,
                textTransform: "uppercase", letterSpacing: 0.8, cursor: "pointer",
              }}>{t}{t === "alerts" && unackCount > 0 ? ` (${unackCount})` : ""}</button>
            ))}
          </div>
          <div style={{ fontFamily: "monospace", color: C.muted, fontSize: 12 }}>
            {time.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })} &nbsp;
            <span style={{ color: C.accent }}>{time.toLocaleTimeString("en-IN", { hour12: false })}</span>
          </div>
          <div style={{ width: 28, height: 28, borderRadius: "50%", background: C.panel, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13 }}>👤</div>
        </div>
      </header>

      <main style={{ padding: "20px 24px", maxWidth: 1600, margin: "0 auto" }}>

        {/* ── OVERVIEW TAB ── */}
        {activeTab === "overview" && (
          <div>
            {/* Stat row */}
            <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
              <StatCard label="Active Cameras" value={activeCams} sub={`${alertCams} in alert`} color={C.green} />
              <StatCard label="Unacked Alerts" value={unackCount} sub="Requires attention" color={unackCount > 0 ? C.red : C.green} pulse={unackCount > 0} />
              <StatCard label="Tracked Vehicles" value={TRACKED_VEHICLES.length} sub="Flagged this session" color={C.amber} />
              <StatCard label="ANPR Reads / hr" value="1,842" sub="Across all cameras" color={C.accent} />
              <StatCard label="Zones Online" value="4/4" sub="All zones nominal" color={C.green} />
            </div>

            {/* Two column: Camera grid + Alerts */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: 16 }}>
              {/* Camera Grid */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Live Camera Grid</span>
                  <span style={{ color: C.muted, fontSize: 11 }}>{CAMERAS.length} feeds</span>
                </div>
                <div style={{ padding: 12, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {CAMERAS.map(cam => (
                    <CameraCard key={cam.id} cam={cam} selected={selectedCam?.id === cam.id} onClick={setSelectedCam} />
                  ))}
                </div>
                {selectedCam && (
                  <div style={{ margin: "0 12px 12px", background: C.panel, border: `1px solid ${C.accent}`, borderRadius: 6, padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                      <span style={{ color: C.accent, fontWeight: 700 }}>{selectedCam.id} — {selectedCam.name}</span>
                      <button onClick={() => setSelectedCam(null)} style={{ background: "transparent", border: "none", color: C.muted, cursor: "pointer", fontSize: 14 }}>✕</button>
                    </div>
                    <div style={{ background: "#000", borderRadius: 4, height: 140, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden" }}>
                      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, #071420, #0A1E32)" }} />
                      <div style={{ position: "relative", textAlign: "center" }}>
                        <div style={{ fontSize: 28, marginBottom: 4 }}>📡</div>
                        <div style={{ color: C.feedMuted, fontSize: 11 }}>RTSP stream renders here in production</div>
                        <div style={{ color: C.feedText, fontSize: 10, fontFamily: "monospace", marginTop: 4 }}>rtsp://sentinel.guj/{selectedCam.id.toLowerCase()}/live</div>
                      </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 10 }}>
                      {[["Zone", selectedCam.zone], ["Status", selectedCam.status.toUpperCase()], ["Lat/Lng", `${selectedCam.lat}, ${selectedCam.lng}`]].map(([k, v]) => (
                        <div key={k} style={{ background: C.surface, borderRadius: 4, padding: "6px 10px" }}>
                          <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>{k}</div>
                          <div style={{ color: C.text, fontSize: 12, marginTop: 2 }}>{v}</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                      {["Snapshot", "Dispatch", "Flag Zone"].map(label => (
                        <button key={label} style={{ flex: 1, background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "6px", fontSize: 11, cursor: "pointer" }}>{label}</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Alert Panel */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Active Alerts</span>
                  <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ color: C.red, fontSize: 11, fontWeight: 700 }}>{critCount} CRITICAL</span>
                    <button onClick={() => setAlerts(prev => prev.map(a => ({ ...a, ack: true })))}
                      style={{ background: "transparent", border: `1px solid ${C.dim}`, color: C.muted, borderRadius: 3, padding: "2px 8px", fontSize: 10, cursor: "pointer" }}>
                      ACK ALL
                    </button>
                  </div>
                </div>
                <div style={{ overflowY: "auto", flex: 1, padding: "8px 0", maxHeight: 520 }}>
                  {alerts.map(a => <AlertRow key={a.id} alert={a} onAck={ackAlert} />)}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── CAMERAS TAB ── */}
        {activeTab === "cameras" && (
          <div>
            <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontWeight: 600 }}>Camera Network — {CAMERAS.length} feeds</div>
              <div style={{ display: "flex", gap: 10 }}>
                {["All", "Zone A", "Zone B", "Zone C", "Zone D"].map(z => (
                  <button key={z} style={{ background: z === "All" ? C.accentGlow : "transparent", border: `1px solid ${z === "All" ? C.accent : C.border}`, color: z === "All" ? C.accent : C.muted, borderRadius: 4, padding: "4px 12px", fontSize: 11, cursor: "pointer" }}>{z}</button>
                ))}
              </div>
            </div>
            {/* Status legend */}
            <div style={{ display: "flex", gap: 16, marginBottom: 14 }}>
              {[["Active", C.green, activeCams], ["Alert", C.red, alertCams], ["Offline", C.muted, 1]].map(([l, c, n]) => (
                <div key={l} style={{ display: "flex", alignItems: "center", gap: 6, color: C.muted, fontSize: 12 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, display: "inline-block" }} />
                  {l} ({n})
                </div>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {CAMERAS.map(cam => <CameraCard key={cam.id} cam={cam} selected={selectedCam?.id === cam.id} onClick={setSelectedCam} />)}
            </div>
          </div>
        )}

        {/* ── VEHICLES TAB ── */}
        {activeTab === "vehicles" && (
          <div>
            <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
              <div style={{ flex: 1, fontWeight: 600, fontSize: 14 }}>Vehicle Tracking — Flagged Vehicles</div>
              <input
                placeholder="Search plate…"
                value={searchPlate}
                onChange={e => setSearchPlate(e.target.value)}
                style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "6px 12px", fontSize: 12, width: 200, outline: "none" }}
              />
              <button style={{ background: C.accentGlow, border: `1px solid ${C.accent}`, color: C.accent, borderRadius: 4, padding: "6px 14px", fontSize: 11, cursor: "pointer" }}>
                + Add to Watchlist
              </button>
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1.4fr 0.8fr 1.2fr 1fr 0.7fr 0.8fr", gap: 8, padding: "8px 12px", background: C.panel, borderBottom: `1px solid ${C.border}` }}>
                {["Plate", "Make", "Color", "Last Camera", "Time", "Flag", "Crossings"].map(h => (
                  <span key={h} style={{ color: C.muted, fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>{h}</span>
                ))}
              </div>
              {filteredVehicles.length === 0
                ? <div style={{ padding: 24, color: C.muted, textAlign: "center" }}>No vehicles match "{searchPlate}"</div>
                : filteredVehicles.map(v => <VehicleRow key={v.plate} v={v} />)
              }
            </div>
            {/* Cross-camera timeline for first vehicle */}
            <div style={{ marginTop: 16, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 12, color: C.accent }}>Cross-Camera Timeline — GJ-01-AB-1234</div>
              <div style={{ display: "flex", gap: 0, alignItems: "center" }}>
                {[["CAM-001", "14:20:10"], ["CAM-002", "14:24:45"], ["CAM-003", "14:32:01"]].map(([cam, t], i) => (
                  <div key={cam} style={{ display: "flex", alignItems: "center" }}>
                    <div style={{ background: C.panel, border: `1px solid ${i === 2 ? C.red : C.border}`, borderRadius: 6, padding: "8px 14px", textAlign: "center" }}>
                      <div style={{ color: i === 2 ? C.red : C.accent, fontFamily: "monospace", fontSize: 11, fontWeight: 700 }}>{cam}</div>
                      <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{t}</div>
                    </div>
                    {i < 2 && <div style={{ width: 40, height: 2, background: C.border, position: "relative" }}>
                      <span style={{ position: "absolute", top: -8, left: 8, color: C.muted, fontSize: 9 }}>→</span>
                    </div>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── ALERTS TAB ── */}
        {activeTab === "alerts" && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ fontWeight: 600 }}>Alert Log — {alerts.length} total, {unackCount} unacknowledged</div>
              <div style={{ display: "flex", gap: 8 }}>
                {["All", "Critical", "High", "Medium", "Low"].map(f => (
                  <button key={f} style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.muted, borderRadius: 4, padding: "4px 12px", fontSize: 11, cursor: "pointer" }}>{f}</button>
                ))}
                <button onClick={() => setAlerts(prev => prev.map(a => ({ ...a, ack: true })))}
                  style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "4px 12px", fontSize: 11, cursor: "pointer" }}>
                  Acknowledge All
                </button>
              </div>
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
              <div style={{ padding: "8px 0", maxHeight: "calc(100vh - 200px)", overflowY: "auto" }}>
                {alerts.map(a => <AlertRow key={a.id} alert={a} onAck={ackAlert} />)}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ── Status Bar ── */}
      <footer style={{ position: "fixed", bottom: 0, left: 0, right: 0, background: C.surface, borderTop: `1px solid ${C.border}`, padding: "6px 24px", display: "flex", alignItems: "center", gap: 24, fontSize: 10, color: C.muted }}>
        <span style={{ color: C.green }}>● SYSTEM OPERATIONAL</span>
        <span>Backend: <span style={{ color: C.text }}>api.sentinel.gujarat.gov.in</span></span>
        <span>Operator: <span style={{ color: C.text }}>ISHA / CMD-01</span></span>
        <span>Shift: <span style={{ color: C.text }}>14:00 – 22:00</span></span>
        <span style={{ marginLeft: "auto" }}>Gujarat Police — Integrated Traffic Management System</span>
      </footer>
    </div>
  );
}
