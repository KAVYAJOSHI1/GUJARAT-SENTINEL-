import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./context/ToastContext.jsx";
import LoginGate from "./components/LoginGate.jsx";
import AppLayout from "./AppLayout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import CamerasPage from "./pages/CamerasPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import IncidentsPage from "./pages/IncidentsPage.jsx";
import IncidentDetailPage from "./pages/IncidentDetailPage.jsx";
import CasesPage from "./pages/CasesPage.jsx";
import CaseDetailPage from "./pages/CaseDetailPage.jsx";
import SystemPage from "./pages/SystemPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
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

        {/* Operational layer — Incident Center + Investigation Cases
            (operational-platform enhancement phase). */}
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="cases/:id" element={<CaseDetailPage />} />

        <Route path="system" element={<SystemPage />} />
        <Route path="admin" element={<AdminPage />} />

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
      <LoginGate>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </LoginGate>
    </ToastProvider>
  );
}
