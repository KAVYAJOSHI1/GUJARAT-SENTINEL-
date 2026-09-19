import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./context/ToastContext.jsx";
import LoginGate from "./components/LoginGate.jsx";
import AppLayout from "./AppLayout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import CommandCenterPage from "./pages/CommandCenterPage.jsx";
import LiveMonitoringPage from "./pages/LiveMonitoringPage.jsx";
import CamerasPage from "./pages/CamerasPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import IncidentsPage from "./pages/IncidentsPage.jsx";
import IncidentDetailPage from "./pages/IncidentDetailPage.jsx";
import CasesPage from "./pages/CasesPage.jsx";
import CaseDetailPage from "./pages/CaseDetailPage.jsx";
import SystemPage from "./pages/SystemPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import SearchPage from "./pages/SearchPage.jsx";
import WatchlistPage from "./pages/WatchlistPage.jsx";
import MyWorkPage from "./pages/MyWorkPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import CopilotPage from "./pages/CopilotPage.jsx";
import AnomaliesPage from "./pages/AnomaliesPage.jsx";
import CameraManagementPage from "./pages/CameraManagementPage.jsx";
import TrafficIntelligencePage from "./pages/TrafficIntelligencePage.jsx";
import CameraIntelligencePage from "./pages/CameraIntelligencePage.jsx";
import AnprIntelligencePage from "./pages/AnprIntelligencePage.jsx";
import InvestigationGraphPage from "./pages/InvestigationGraphPage.jsx";
import LiveInvestigationWorkspace from "./pages/LiveInvestigationWorkspace.jsx";
import InvestigationPage from "./pages/InvestigationPage.jsx";
import MapPage from "./pages/MapPage.jsx";
import LiveCameraAIPage from "./pages/LiveCameraAIPage.jsx";

// Route table, exported without a router so it can be mounted under any
// router (BrowserRouter in the app, MemoryRouter in smoke tests).
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {/* Phase 16 — Command Center is the primary landing page.
            The Phase 10 dashboard stays reachable at /dashboard. */}
        <Route index element={<CommandCenterPage />} />
        <Route path="command-center" element={<CommandCenterPage />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="live-monitoring" element={<LiveMonitoringPage />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="cameras/manage" element={<CameraManagementPage />} />
        <Route path="alerts" element={<AlertsPage />} />

        {/* Operational layer — Incident Center + Investigation Cases
            (operational-platform enhancement phase). */}
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="cases/:id" element={<CaseDetailPage />} />

        {/* Phase 11 — advanced operational features */}
        <Route path="search" element={<SearchPage />} />
        <Route path="watchlists" element={<WatchlistPage />} />
        <Route path="my-work" element={<MyWorkPage />} />
        <Route path="reports" element={<ReportsPage />} />

        {/* Phase 12 — AI intelligence layer */}
        <Route path="copilot" element={<CopilotPage />} />
        <Route path="anomalies" element={<AnomaliesPage />} />

        {/* Phase 14 — advanced video intelligence */}
        <Route path="traffic" element={<TrafficIntelligencePage />} />
        <Route path="camera-intelligence" element={<CameraIntelligencePage />} />
        <Route path="anpr-intelligence" element={<AnprIntelligencePage />} />
        <Route path="graph" element={<InvestigationGraphPage />} />
        <Route path="workspace" element={<LiveInvestigationWorkspace />} />
        <Route path="live-camera-ai" element={<LiveCameraAIPage />} />

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
