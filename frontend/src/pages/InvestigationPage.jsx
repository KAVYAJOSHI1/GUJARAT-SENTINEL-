import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { Download, FileSpreadsheet, MapPin, MapPinned, Radio, Search } from "lucide-react";
import { C, CAMERA_STATUS_COLOR } from "../theme.js";
import { useToast } from "../context/ToastContext.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import GisMap from "../components/gis/GisMap.jsx";
import CameraMarker from "../components/gis/CameraMarker.jsx";
import RoutePolyline from "../components/gis/RoutePolyline.jsx";
import EvidenceModal from "../components/gis/EvidenceModal.jsx";
import SearchBar from "../components/investigation/SearchBar.jsx";
import VehicleProfileCard from "../components/investigation/VehicleProfileCard.jsx";
import SightingTimeline from "../components/investigation/SightingTimeline.jsx";
import { fetchCamerasGeoJSON, searchVehicle } from "../services/investigationApi.js";
import { exportVehicleReportCSV, exportVehicleReportPDF } from "../utils/reportExporter.js";
import { CITY_ZOOM, FOCUS_ZOOM, GUJARAT_CENTER, GUJARAT_ZOOM } from "../lib/mockGisData.js";
import { formatPlate } from "../utils/plate.js";

// Hero feature: GIS Mapping + Vehicle Investigation console (DEVELOPER_README §2).
// Rendered inside Isha's AppLayout via App.jsx; reads the shared data layer from
// <Outlet context> and honours the CameraModal hand-off (`/investigation?cam=<id>`).
//
// Layout:  search bar → vehicle profile + export → [ timeline | GIS map ] → evidence modal
export default function InvestigationPage() {
  const { cameras: layoutCameras = [], backendLive, loading: layoutLoading } = useOutletContext() || {};
  const { push } = useToast();
  const [params, setParams] = useSearchParams();
  const camParam = params.get("cam");
  const plateParam = params.get("plate");

  const [gisCameras, setGisCameras] = useState([]);
  const [gisLoaded, setGisLoaded] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [live, setLive] = useState(true);
  const [selected, setSelected] = useState(null);
  const [showAllCameras, setShowAllCameras] = useState(false);
  const lastPlate = useRef(null);

  // Base camera layer: prefer the dedicated GeoJSON endpoint, fall back to the
  // cameras already loaded once by AppLayout so we don't double-fetch.
  useEffect(() => {
    let cancelled = false;
    fetchCamerasGeoJSON().then((res) => {
      if (cancelled) return;
      if (res.data?.length) setGisCameras(res.data);
      else if (layoutCameras.length) setGisCameras(layoutCameras);
      setGisLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [layoutCameras]);

  const runSearch = useCallback(async (plate, range) => {
    lastPlate.current = plate;
    setLoading(true);
    setSearched(true);
    const res = await searchVehicle(plate, range || {});
    setResult(res.data);
    setLive(res.live);
    setSelected(null);
    setLoading(false);

    const n = res.data?.sightings?.length || 0;
    const plateLabel = formatPlate(res.data?.plate || plate);
    if (n > 0) {
      push({
        id: `search-${plateLabel}-${Date.now()}`,
        title: "Vehicle found",
        msg: `Vehicle ${plateLabel} found across ${n} camera sighting${n === 1 ? "" : "s"}.`,
        severity: res.data?.watchlistHit ? "high" : "medium",
      });
    }
  }, [push]);

  // Auto-run when arriving with ?plate= (deep link / dashboard hand-off), once.
  useEffect(() => {
    if (plateParam && plateParam !== lastPlate.current) runSearch(plateParam);
  }, [plateParam, runSearch]);

  const handleSearch = (plate, range) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("plate", plate);
        return next;
      },
      { replace: true }
    );
    runSearch(plate, range);
  };

  // Resolve the ?cam=<id> hand-off. Look in the GIS inventory first, then fall
  // back to the cameras AppLayout already loaded (Isha's dashboard links use
  // that id set), and require real coordinates so we can actually centre on it.
  const focusCamera = useMemo(() => {
    if (!camParam) return null;
    const hit = [...gisCameras, ...layoutCameras].find(
      (c) => c.id === camParam && Number.isFinite(c.lat) && Number.isFinite(c.lng)
    );
    if (!hit) return null;
    return {
      id: hit.id,
      name: hit.name,
      district: hit.district ?? hit.zone ?? "—",
      status: hit.status ?? "active",
      lat: hit.lat,
      lng: hit.lng,
    };
  }, [camParam, gisCameras, layoutCameras]);

  // camera requested in the URL but absent from every loaded inventory
  // (only decided once both camera sources have settled, to avoid a flash)
  const camNotFound = Boolean(camParam) && gisLoaded && !layoutLoading && !focusCamera;

  const sightings = result?.sightings || [];
  const hasSightings = sightings.length > 0;

  // Markers to draw: the GIS inventory, plus the focused camera itself if it
  // only exists in AppLayout's set (so it can still be highlighted).
  const mapCameras = useMemo(() => {
    if (focusCamera && !gisCameras.some((c) => c.id === focusCamera.id)) {
      return [...gisCameras, focusCamera];
    }
    return gisCameras;
  }, [gisCameras, focusCamera]);

  // Camera-focus mode: opened on one camera, no vehicle route drawn yet.
  const focusMode = Boolean(focusCamera) && !hasSightings;

  // In focus mode, keep the map uncluttered: show the selected camera plus only
  // its nearest neighbours for context, unless the user asks for the full grid.
  const nearbyCameras = useMemo(() => {
    if (!focusMode) return [];
    const d2 = (c) => (c.lat - focusCamera.lat) ** 2 + (c.lng - focusCamera.lng) ** 2;
    return mapCameras
      .filter((c) => c.id !== focusCamera.id && Number.isFinite(c.lat) && Number.isFinite(c.lng))
      .sort((a, b) => d2(a) - d2(b))
      .slice(0, 6);
  }, [focusMode, focusCamera, mapCameras]);

  const preSearchCameras =
    focusMode && !showAllCameras ? [focusCamera, ...nearbyCameras] : mapCameras;

  // When opened on a specific camera (and no route is drawn) pan the map onto it.
  const spotlight = focusMode
    ? { lat: focusCamera.lat, lng: focusCamera.lng, zoom: FOCUS_ZOOM }
    : null;

  const mapCenter = hasSightings
    ? [sightings[0].lat, sightings[0].lng]
    : focusCamera
    ? [focusCamera.lat, focusCamera.lng]
    : GUJARAT_CENTER;
  const mapZoom = hasSightings ? CITY_ZOOM : focusCamera ? FOCUS_ZOOM : GUJARAT_ZOOM;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {!backendLive && (
        <ErrorBanner message="Backend connection lost — investigation running on simulated data." />
      )}

      {camNotFound && (
        <ErrorBanner
          message={`Camera “${camParam}” was not found in the network inventory — showing the full Gujarat camera map.`}
        />
      )}

      {/* ── Title + search ─────────────────────────────────────────────── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <MapPinned size={16} color={C.accent} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>Vehicle Investigation Console</span>
          {live === false && searched && (
            <span style={{ display: "flex", alignItems: "center", gap: 4, color: C.amber, fontSize: 10, border: `1px solid ${C.amber}55`, borderRadius: 3, padding: "1px 6px" }}>
              <Radio size={10} /> SIMULATED DATA
            </span>
          )}
        </div>
        <div style={{ color: C.muted, fontSize: 11, marginBottom: 10 }}>
          Enter a registration plate to trace a vehicle&rsquo;s chronological movement across the Gujarat CCTV grid.
        </div>

        {focusCamera && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
              background: C.panel,
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              padding: "8px 12px",
              marginBottom: 10,
              fontSize: 11,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: C.accent, fontWeight: 700 }}>
              <MapPin size={13} /> Selected camera
            </span>
            <strong style={{ color: C.text }}>
              {focusCamera.id} — {focusCamera.name}
            </strong>
            <span style={{ color: C.muted }}>· {focusCamera.district}</span>
            <span
              style={{
                textTransform: "uppercase",
                letterSpacing: 0.6,
                fontSize: 9,
                fontWeight: 700,
                borderRadius: 3,
                padding: "1px 6px",
                color: CAMERA_STATUS_COLOR[focusCamera.status] || C.green,
                border: `1px solid ${CAMERA_STATUS_COLOR[focusCamera.status] || C.green}55`,
              }}
            >
              {focusCamera.status}
            </span>
            {focusCamera.lat != null && (
              <span style={{ color: C.dim, fontFamily: "monospace" }}>
                {focusCamera.lat.toFixed(5)}, {focusCamera.lng.toFixed(5)}
              </span>
            )}
          </div>
        )}

        <SearchBar initialPlate={plateParam || ""} loading={loading} onSearch={handleSearch} />
      </div>

      {loading && (
        <div style={{ color: C.muted, fontSize: 12, padding: "8px 0" }}>Searching camera network…</div>
      )}

      {/* ── Empty state ────────────────────────────────────────────────── */}
      {searched && !loading && !hasSightings && (
        <EmptyState
          icon={MapPinned}
          title={`No recorded sightings found for plate ${result ? formatPlate(result.plate) : ""}`}
          hint="Check the plate number or widen the date range."
        />
      )}

      {/* ── Results ────────────────────────────────────────────────────── */}
      {hasSightings && (
        <>
          <div style={{ display: "flex", gap: 12, alignItems: "stretch", flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 320px" }}>
              <VehicleProfileCard result={result} />
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 8,
                justifyContent: "center",
                minWidth: 190,
              }}
            >
              <button onClick={() => exportVehicleReportPDF(result)} style={pdfBtn}>
                <Download size={14} /> Export PDF Report
              </button>
              <button onClick={() => exportVehicleReportCSV(result)} style={csvBtn}>
                <FileSpreadsheet size={13} /> Export CSV
              </button>
            </div>
          </div>

          <div className="investigation-grid">
            {/* LEFT — chronological timeline */}
            <section style={panel}>
              <div style={panelHead}>
                <span>Movement Timeline</span>
                <span style={{ color: C.muted, fontWeight: 400 }}>{sightings.length} sightings · ASC</span>
              </div>
              <div style={{ padding: "8px 12px", overflowY: "auto", maxHeight: 520 }}>
                <SightingTimeline sightings={sightings} activeId={selected?.eventId} onSelect={setSelected} />
              </div>
            </section>

            {/* RIGHT — GIS map + trajectory */}
            <section style={panel}>
              <div style={panelHead}>
                <span>Route Trajectory</span>
                <span style={{ color: C.muted, fontWeight: 400 }}>polyline + direction arrows</span>
              </div>
              <div style={{ padding: 12 }}>
                <GisMap center={mapCenter} zoom={mapZoom} height={496}>
                  {mapCameras.map((cam) => (
                    <CameraMarker
                      key={cam.id}
                      camera={cam}
                      highlighted={cam.id === focusCamera?.id}
                      dim={Boolean(focusCamera) && cam.id !== focusCamera.id}
                    />
                  ))}
                  <RoutePolyline sightings={sightings} />
                </GisMap>
              </div>
            </section>
          </div>
        </>
      )}

      {/* ── Pre-search browse map ──────────────────────────────────────── */}
      {!searched && !loading && (
        <section style={panel}>
          <div style={panelHead}>
            <span>{focusCamera ? `Selected Camera · ${focusCamera.id}` : "Gujarat Camera Network"}</span>
            {focusMode ? (
              <button
                type="button"
                onClick={() => setShowAllCameras((v) => !v)}
                style={{
                  background: "transparent",
                  border: `1px solid ${C.border}`,
                  color: C.muted,
                  borderRadius: 4,
                  padding: "3px 10px",
                  fontSize: 10,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {showAllCameras ? "Show nearby only" : `Show all ${mapCameras.length} cameras`}
              </button>
            ) : (
              <span style={{ color: C.muted, fontWeight: 400, display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Search size={11} /> run a plate search to trace a route
              </span>
            )}
          </div>
          <div style={{ padding: 12 }}>
            <GisMap center={mapCenter} zoom={mapZoom} height={340} focus={spotlight}>
              {preSearchCameras.map((cam) => (
                <CameraMarker
                  key={cam.id}
                  camera={cam}
                  highlighted={cam.id === focusCamera?.id}
                  dim={focusMode && cam.id !== focusCamera.id}
                />
              ))}
            </GisMap>
          </div>
        </section>
      )}

      <EvidenceModal
        sighting={selected}
        plate={result ? formatPlate(result.plate) : ""}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}

const panel = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 8,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const panelHead = {
  padding: "10px 14px",
  borderBottom: `1px solid ${C.border}`,
  fontWeight: 600,
  fontSize: 12,
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 8,
};

const pdfBtn = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 7,
  background: C.accent,
  border: `1px solid ${C.accent}`,
  color: "#0b0f14",
  borderRadius: 4,
  padding: "10px 16px",
  fontSize: 12.5,
  fontWeight: 700,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const csvBtn = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  background: "transparent",
  border: `1px solid ${C.border}`,
  color: C.muted,
  borderRadius: 4,
  padding: "7px 14px",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};
