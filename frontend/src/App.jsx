import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./context/ToastContext.jsx";
import AppLayout from "./AppLayout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import CamerasPage from "./pages/CamerasPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import InvestigationPage from "./pages/InvestigationPage.jsx";
import MapPage from "./pages/MapPage.jsx";

// Route table, exported without a router so it can be mounted under any
// router (BrowserRouter in the app, MemoryRouter in smoke tests).
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="alerts" element={<AlertsPage />} />

        {/* GIS Mapping + Vehicle Investigation console
            (Vishakha · feature/vishakha-investigation). */}
        <Route path="investigation" element={<InvestigationPage />} />
        <Route path="map" element={<MapPage />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ToastProvider>
  );
}
