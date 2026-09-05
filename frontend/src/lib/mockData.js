// ─── Simulated data ──────────────────────────────────────────────────────────
// Used as an offline fallback when Vanshal's backend is unreachable, and as the
// seed for the simulated live-alert stream in useAlertsSocket.js.
// Shapes mirror the assumed docs/API_CONTRACTS.md schemas (see services/api.js
// for the normalisers that make real + mock data interchangeable).

export const CAMERAS = [
  { id: "CAM-001", name: "Sardar Bridge", zone: "Zone A", lat: 23.022, lng: 72.571, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-002", name: "Manek Chowk", zone: "Zone A", lat: 23.025, lng: 72.587, status: "active", resolution: "1920x1080", fps: 30, protocol: "RTSP" },
  { id: "CAM-003", name: "Kalupur Junction", zone: "Zone B", lat: 23.035, lng: 72.605, status: "alert", resolution: "2560x1440", fps: 25, protocol: "WebRTC" },
  { id: "CAM-004", name: "Sola Highway", zone: "Zone C", lat: 23.071, lng: 72.529, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-005", name: "Naranpura Gate", zone: "Zone B", lat: 23.054, lng: 72.553, status: "offline", resolution: "1280x720", fps: 15, protocol: "RTSP" },
  { id: "CAM-006", name: "GIFT City Entry", zone: "Zone D", lat: 23.157, lng: 72.683, status: "active", resolution: "3840x2160", fps: 30, protocol: "WebRTC" },
  { id: "CAM-007", name: "Iskcon Cross Roads", zone: "Zone C", lat: 23.028, lng: 72.507, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-008", name: "Nehru Bridge", zone: "Zone A", lat: 23.026, lng: 72.575, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-009", name: "Vastrapur Lake", zone: "Zone C", lat: 23.038, lng: 72.526, status: "active", resolution: "1920x1080", fps: 30, protocol: "RTSP" },
  { id: "CAM-010", name: "Shivranjani Junction", zone: "Zone C", lat: 23.023, lng: 72.531, status: "alert", resolution: "2560x1440", fps: 25, protocol: "WebRTC" },
  { id: "CAM-011", name: "Chandkheda Circle", zone: "Zone D", lat: 23.108, lng: 72.581, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-012", name: "Naroda Patiya", zone: "Zone B", lat: 23.069, lng: 72.657, status: "active", resolution: "1280x720", fps: 20, protocol: "RTSP" },
  { id: "CAM-013", name: "Paldi Char Rasta", zone: "Zone A", lat: 23.011, lng: 72.564, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
  { id: "CAM-014", name: "Bopal Circle", zone: "Zone C", lat: 23.032, lng: 72.470, status: "offline", resolution: "1280x720", fps: 15, protocol: "RTSP" },
  { id: "CAM-015", name: "Airport Circle", zone: "Zone D", lat: 23.075, lng: 72.626, status: "active", resolution: "3840x2160", fps: 30, protocol: "WebRTC" },
  { id: "CAM-016", name: "Maninagar Station", zone: "Zone B", lat: 22.998, lng: 72.601, status: "active", resolution: "1920x1080", fps: 25, protocol: "RTSP" },
];

export const INITIAL_ALERTS = [
  { id: 1, type: "ANPR_MATCH", cam: "CAM-003", vehicle: "GJ-01-AB-1234", severity: "critical", msg: "Watchlist vehicle detected — stolen vehicle", time: "14:32:01", ack: false },
  { id: 2, type: "CROWD_ANOMALY", cam: "CAM-002", vehicle: null, severity: "high", msg: "Abnormal crowd density detected", time: "14:30:48", ack: false },
  { id: 3, type: "WRONG_WAY", cam: "CAM-001", vehicle: "GJ-05-CD-5678", severity: "medium", msg: "Wrong-way vehicle on Sardar Bridge", time: "14:28:15", ack: true },
  { id: 4, type: "ANPR_MATCH", cam: "CAM-004", vehicle: "GJ-18-XY-9900", severity: "high", msg: "Suspect vehicle — outstanding warrant", time: "14:25:00", ack: false },
  { id: 5, type: "LOITERING", cam: "CAM-010", vehicle: null, severity: "low", msg: "Loitering detected near junction island", time: "14:22:37", ack: true },
];

// Recent watchlist detections shown on the dashboard. Full vehicle search
// history / trajectory is owned by Vishakha (feature/vishakha-investigation).
export const WATCHLIST_DETECTIONS = [
  { plate: "GJ-01-AB-1234", make: "Maruti Swift", color: "Red", lastSeen: "CAM-003", time: "14:32:01", flag: "STOLEN" },
  { plate: "GJ-18-XY-9900", make: "Toyota Innova", color: "White", lastSeen: "CAM-004", time: "14:25:00", flag: "WARRANT" },
  { plate: "GJ-05-CD-5678", make: "Tata Nexon", color: "Blue", lastSeen: "CAM-001", time: "14:28:15", flag: "TRAFFIC" },
];

export const MOCK_STATS = {
  totalCameras: CAMERAS.length,
  onlineFeeds: CAMERAS.filter((c) => c.status !== "offline").length,
  activeAlerts: INITIAL_ALERTS.filter((a) => !a.ack).length,
  todaysDetections: 1842,
  anprReadsPerHour: 1842,
  zonesOnline: "4/4",
};

const SIM_TYPES = [
  { type: "SPEED_VIOLATION", msg: "Speed limit exceeded — 78 km/h in 50 zone", severity: ["low", "medium"] },
  { type: "WRONG_WAY", msg: "Wrong-way movement detected at junction", severity: ["medium", "high"] },
  { type: "SIGNAL_JUMP", msg: "Red-light violation captured", severity: ["low", "medium"] },
  { type: "ANPR_MATCH", msg: "Watchlist plate seen at junction", severity: ["high", "critical"] },
];

// Produce one plausible alert payload for the simulated live stream.
export function makeSimulatedAlert() {
  const kind = SIM_TYPES[Math.floor(Math.random() * SIM_TYPES.length)];
  const severity = kind.severity[Math.floor(Math.random() * kind.severity.length)];
  const cam = CAMERAS[Math.floor(Math.random() * CAMERAS.length)];
  const withPlate = kind.type === "ANPR_MATCH" || Math.random() > 0.4;
  return {
    id: `sim-${Date.now()}`,
    type: kind.type,
    cam: cam.id,
    vehicle: withPlate
      ? `GJ-${String(Math.floor(Math.random() * 38) + 1).padStart(2, "0")}-${
          "ABCDEFGHJK"[Math.floor(Math.random() * 10)]
        }${"LMNPQRSTUV"[Math.floor(Math.random() * 10)]}-${Math.floor(Math.random() * 9000 + 1000)}`
      : null,
    severity,
    msg: kind.msg,
    time: new Date().toLocaleTimeString("en-IN", { hour12: false }),
    ack: false,
    // Never let this be mistaken for a live government-feed alert
    // (SENTINEL_System_Audit_Report.md §14/§16/§20 — "a judge could be
    // shown fabricated 'live' alerts without any visual difference").
    // normalizeAlert() in services/api.js carries this straight through;
    // AlertRow renders a visible SIMULATED tag whenever it's set.
    simulated: true,
  };
}
