import { Outlet } from "react-router-dom";
import { C } from "./theme.js";
import Navbar from "./components/Navbar.jsx";
import Footer from "./components/Footer.jsx";
import ToastContainer from "./components/toast/ToastContainer.jsx";
import { useSentinelData } from "./hooks/useSentinelData.js";

// App shell: persistent header + footer, routed page in between, global toast
// stack. The shared data layer is created once here and passed to pages via
// <Outlet context> so every route reads the same live state.
export default function AppLayout() {
  const data = useSentinelData();

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: C.bg, color: C.text }}>
      <Navbar wsStatus={data.wsStatus} unackCount={data.unackCount} critCount={data.critCount} />

      <main className="app-main" style={{ flex: 1, width: "100%" }}>
        <Outlet context={data} />
      </main>

      <Footer backendLive={data.backendLive} />
      <ToastContainer />
    </div>
  );
}
