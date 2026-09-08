import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import {
  Camera,
  Download,
  FileSpreadsheet,
  MapPin,
  MapPinned,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Search,
} from "lucide-react";
import { C, CAMERA_STATUS_COLOR } from "../theme.js";
import { useToast } from "../context/ToastContext.jsx";
import { isMockCamera } from "../services/api.js";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import GisMap from "../components/gis/GisMap.jsx";
import CameraMarker from "../components/gis/CameraMarker.jsx";
import RoutePolyline from "../components/gis/RoutePolyline.jsx";
import EvidenceModal from "../components/gis/EvidenceModal.jsx";
import SearchBar from "../components/investigation/SearchBar.jsx";
import VehicleProfileCard from "../components/investigation/VehicleProfileCard.jsx";
import SightingTimeline from "../components/investigation/SightingTimeline.jsx";
import JourneyIntelligence from "../components/investigation/JourneyIntelligence.jsx";
import VisualMatchesPanel from "../components/investigation/VisualMatchesPanel.jsx";
import { fetchCamerasGeoJSON, searchVehicle } from "../services/investigationApi.js";
import { exportVehicleReportCSV, exportVehicleReportPDF } from "../utils/reportExporter.js";
import { CITY_ZOOM, FOCUS_ZOOM, GUJARAT_CENTER, GUJARAT_ZOOM } from "../lib/mockGisData.js";
import { formatPlate } from "../utils/plate.js";

const PLAY_STEP_MS = 2500;

// Hero feature: GIS Mapping + Vehicle Investigation console (DEVELOPER_README §2).
// Rendered inside Isha's AppLayout via App.jsx; reads the shared data layer from
// <Outlet context> and honours the CameraModal hand-off (`/investigation?cam=<id>`).
//
// Layout:  search bar → vehicle profile + export → [ timeline | GIS map ] → evidence modal
export default function InvestigationPage() {
  const { cameras: layoutCameras = [], backendLive, loading: layoutLoading } = useOutletContext() || {};
  const { push } = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const camParam = params.get("cam");
  const plateParam = params.get("plate");

  const [gisCameras, setGisCameras] = useState([]);
  const [gisLoaded, setGisLoaded] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [live, setLive] = useState(true);
  // `selected` drives timeline highlight + map fly-to/marker highlight + the
  // inline detail panel -- lightweight, never blocks the map. Opening the
  // full evidence viewer is a separate, explicit action (`evidenceTarget`),
  // so autoplay never pops a screen-covering modal on every step.
  const [selected, setSelected] = useState(null);
  const [evidenceTarget, setEvidenceTarget] = useState(null);
  const [showAllCameras, setShowAllCameras] = useState(false);

  // ── Play Journey (§7) ──────────────────────────────────────────────────
  const [playing, setPlaying] = useState(false);
  const [playIndex, setPlayIndex] = useState(-1);

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
    setEvidenceTarget(null);
    setPlaying(false);
    setPlayIndex(-1);
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

  // Advances one sighting every PLAY_STEP_MS while playing. This is
  // deliberately NOT a moving-vehicle animation (§7 explicitly forbids
  // that) -- it just steps the same selection state a manual click would
  // set, in order: "observed here, then here, then here."
  useEffect(() => {
    if (!playing || sightings.length === 0) return undefined;
    const idx = Math.max(0, playIndex);
    setSelected(sightings[idx]);
    const t = setTimeout(() => {
      if (idx + 1 < sightings.length) {
        setPlayIndex(idx + 1);
      } else {
        setPlaying(false); // finished at the final sighting
      }
    }, PLAY_STEP_MS);
    return () => clearTimeout(t);
  }, [playing, playIndex, sightings]);

  const handlePlay = useCallback(() => {
    if (sightings.length === 0) return;
    setPlayIndex((i) => (i < 0 || i >= sightings.length - 1 ? 0 : i));
    setPlaying(true);
  }, [sightings.length]);

  const handlePause = useCallback(() => setPlaying(false), []);

  const handleResetJourney = useCallback(() => {
    setPlaying(false);
    setPlayIndex(-1);
    setSelected(null);
  }, []);

  // Any manual selection (timeline row / map marker click) interrupts autoplay.
  const handleSelectSighting = useCallback((s) => {
    setPlaying(false);
    setSelected(s);
  }, []);

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

  // Journey task §6: selecting a sighting (click, or Play Journey stepping
  // through) pans the map to it -- only when it actually has a camera fix
  // (§4: a sighting without coordinates stays visible in the timeline but
  // can't be plotted or flown to).
  const journeyFocus = selected?.hasLocation
    ? { lat: selected.lat, lng: selected.lng, zoom: Math.max(mapZoom, FOCUS_ZOOM) }
    : null;

  const selectedIndex = selected ? sightings.findIndex((s) => s.eventId === selected.eventId) : -1;

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
              <button
                onClick={() => navigate(
                  `/copilot?plate=${encodeURIComponent(result.plate)}` +
                  `&q=${encodeURIComponent(`Show the journey of ${result.plate}`)}`
                )}
                style={csvBtn}
              >
                <Search size={13} /> Ask AI about this vehicle
              </button>
              <button
                onClick={() => navigate(`/graph?plate=${encodeURIComponent(result.plate)}`)}
                style={csvBtn}
              >
                <Search size={13} /> Investigation graph
              </button>
            </div>
          </div>

          {/* Journey task §4/§7: labelled explicitly as camera sightings, not
              GPS tracking, with the Play Journey transport controls. */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13, color: C.text, letterSpacing: 0.4 }}>
                VEHICLE JOURNEY — CAMERA SIGHTINGS
              </div>
              <div style={{ color: C.dim, fontSize: 10.5, marginTop: 2 }}>
                Chronological trail of camera sightings, not live GPS tracking.
              </div>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={playing ? handlePause : handlePlay}
                style={{ ...journeyBtn, borderColor: C.accent, color: C.accent }}
                title={playing ? "Pause journey playback" : "Play journey"}
              >
                {playing ? <Pause size={12} /> : <Play size={12} />} {playing ? "Pause" : "Play journey"}
              </button>
              <button onClick={handleResetJourney} style={journeyBtn} title="Reset playback">
                <RotateCcw size={12} /> Reset
              </button>
            </div>
          </div>

          <JourneyIntelligence result={result} onSelectCamera={handleSelectSighting} />

          <VisualMatchesPanel plate={result?.plate} />

          <div className="investigation-grid">
            {/* LEFT — chronological timeline */}
            <section style={panel}>
              <div style={panelHead}>
                <span>Movement Timeline</span>
                <span style={{ color: C.muted, fontWeight: 400 }}>{sightings.length} sightings · ASC</span>
              </div>
              <div style={{ padding: "8px 12px", overflowY: "auto", maxHeight: 520 }}>
                <SightingTimeline sightings={sightings} activeId={selected?.eventId} onSelect={handleSelectSighting} />
              </div>
            </section>

            {/* RIGHT — GIS map + trajectory + selected-sighting detail */}
            <section style={panel}>
              <div style={panelHead}>
                <span>Camera Sighting Trail</span>
                <span style={{ color: C.muted, fontWeight: 400 }}>
                  {playing
                    ? `playing · ${selectedIndex + 1}/${sightings.length}`
                    : result?.hasJourney
                    ? "sightings connected in time order"
                    : result?.isSingleSighting
                    ? "single sighting — nothing to connect"
                    : "not enough geolocated sightings to draw a trail"}
                </span>
              </div>
              <div style={{ padding: 12 }}>
                <GisMap center={mapCenter} zoom={mapZoom} height={selected ? 380 : 496} focus={journeyFocus}>
                  {mapCameras.map((cam) => (
                    <CameraMarker
                      key={cam.id}
                      camera={cam}
                      highlighted={cam.id === focusCamera?.id}
                      dim={Boolean(focusCamera) && cam.id !== focusCamera.id}
                    />
                  ))}
                  <RoutePolyline sightings={sightings} activeId={selected?.eventId} onSelect={handleSelectSighting} />
                </GisMap>

                {/* Journey task §5: clicking a marker/timeline row opens this
                    detail panel -- inline, not a blocking modal, so playback
                    and manual browsing never hide the map. */}
                {selected && (
                  <div style={{ marginTop: 10, background: C.panel, border: `1px solid ${C.accent}`, borderRadius: 6, padding: "10px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 12 }}>
                        <span style={{ color: C.accent, fontFamily: "monospace" }}>
                          #{selectedIndex + 1} {selected.cameraId}
                        </span>
                        {isMockCamera(selected.cameraCode || selected.cameraId) && (
                          <span style={{ color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 4px", fontSize: 8, fontWeight: 700 }}>
                            MOCK
                          </span>
                        )}
                      </span>
                      <span style={{ color: C.muted, fontSize: 10, fontFamily: "monospace" }}>
                        {selected.timestamp ? new Date(selected.timestamp).toLocaleString("en-IN", { hour12: false }) : "—"}
                      </span>
                    </div>
                    <div style={{ color: C.muted, fontSize: 11, marginTop: 3 }}>
                      {selected.locationDesc || selected.cameraName}
                      {!selected.hasLocation && <span style={{ color: C.amber }}> · location unavailable</span>}
                    </div>
                    <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap", fontSize: 11 }}>
                      <span>
                        Plate: <strong style={{ color: C.text, fontFamily: "monospace" }}>{result?.plate ? formatPlate(result.plate) : "—"}</strong>
                      </span>
                      <span>
                        Confidence:{" "}
                        <strong style={{ color: C.text }}>
                          {Number.isFinite(selected.ocrConfidence) ? `${(selected.ocrConfidence * 100).toFixed(1)}%` : "—"}
                        </strong>
                      </span>
                      <span>
                        Vehicle: <strong style={{ color: C.text }}>{selected.vehicleType || "—"}</strong>
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                      <button onClick={() => setEvidenceTarget(selected)} style={journeyBtn}>
                        <Camera size={11} /> View evidence
                      </button>
                      <button
                        onClick={() =>
                          setParams((prev) => {
                            const next = new URLSearchParams(prev);
                            next.set("cam", selected.cameraId);
                            return next;
                          })
                        }
                        style={journeyBtn}
                      >
                        <MapPinned size={11} /> Open camera
                      </button>
                    </div>
                  </div>
                )}
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
        sighting={evidenceTarget}
        plate={result ? formatPlate(result.plate) : ""}
        onClose={() => setEvidenceTarget(null)}
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

const journeyBtn = {
  display: "flex",
  alignItems: "center",
  gap: 5,
  background: "transparent",
  border: `1px solid ${C.border}`,
  color: C.muted,
  borderRadius: 4,
  padding: "5px 10px",
  fontSize: 10.5,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};
