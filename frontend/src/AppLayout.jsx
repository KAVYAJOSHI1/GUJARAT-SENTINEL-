import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { C } from "./theme.js";
import Navbar from "./components/Navbar.jsx";
import Footer from "./components/Footer.jsx";
import ToastContainer from "./components/toast/ToastContainer.jsx";
import { useSentinelData } from "./hooks/useSentinelData.js";

// Route → browser tab title (Phase 13 UI consistency). Keeps the tab
// meaningful as an officer moves around the command centre.
const TITLES = {
  "/": "Command Center",
  "/copilot": "AI Investigation Copilot",
  "/my-work": "My Work",
  "/cameras": "Camera Network",
  "/cameras/manage": "Camera Management",
  "/camera-intelligence": "Camera Reliability Intelligence",
  "/anpr-intelligence": "ANPR Intelligence",
  "/alerts": "Alerts",
  "/anomalies": "AI Anomaly Detection",
  "/traffic": "Traffic Intelligence",
  "/incidents": "Incident Center",
  "/cases": "Investigation Cases",
  "/search": "Advanced Search",
  "/watchlists": "Watchlist Management",
  "/reports": "Reports Center",
  "/map": "GIS Map",
  "/system": "System",
  "/admin": "Activity / Audit Log",
  "/investigation": "Vehicle Investigation",
  "/graph": "Investigation Graph",
  "/workspace": "Investigation Workspace",
};

function titleFor(pathname) {
  if (TITLES[pathname]) return TITLES[pathname];
  if (pathname.startsWith("/incidents/")) return "Incident Detail";
  if (pathname.startsWith("/cases/")) return "Case Detail";
  return "Command Center";
}

// App shell: persistent header + footer, routed page in between, global toast
// stack. The shared data layer is created once here and passed to pages via
// <Outlet context> so every route reads the same live state.
export default function AppLayout() {
  const data = useSentinelData();
  const { pathname } = useLocation();

  useEffect(() => {
    document.title = `SENTINEL — ${titleFor(pathname)}`;
  }, [pathname]);

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg, color: C.text }}>
      <Navbar
        wsStatus={data.wsStatus}
        unackCount={data.unackCount}
        critCount={data.critCount}
        notifUnread={data.notifUnread}
      />

      <main className="app-main" style={{ flex: 1, width: "100%" }}>
        <Outlet context={data} />
      </main>

      <Footer backendLive={data.backendLive} />
      <ToastContainer />
    </div>
  );
}
