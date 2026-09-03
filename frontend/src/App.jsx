import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./context/ToastContext.jsx";
import AppLayout from "./AppLayout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import CamerasPage from "./pages/CamerasPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import InvestigationPlaceholder from "./pages/InvestigationPlaceholder.jsx";

// Route table, exported without a router so it can be mounted under any
// router (BrowserRouter in the app, MemoryRouter in smoke tests).
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="alerts" element={<AlertsPage />} />

        {/* Owned by Vishakha (feature/vishakha-investigation).
            Placeholder until InvestigationPage.jsx / components/gis land. */}
        <Route path="investigation" element={<InvestigationPlaceholder />} />
        <Route path="map" element={<InvestigationPlaceholder />} />

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
