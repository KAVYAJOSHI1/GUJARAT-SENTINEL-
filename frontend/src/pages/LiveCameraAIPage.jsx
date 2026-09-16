import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Car, VideoOff } from "lucide-react";
import { C } from "../theme.js";
import {
  annotatedStreamUrl,
  fetchCameraStatus,
  fetchLiveCameraList,
  rawStreamUrl,
} from "../services/liveCameraApi.js";

const STATUS_STYLE = {
  ONLINE: { c: C.green, label: "ONLINE" },
  RECONNECTING: { c: C.amber, label: "RECONNECTING" },
  OFFLINE: { c: C.red, label: "OFFLINE" },
};

const POLL_MS = 2000;

// "Live Camera & AI" page -- the real Sentinel RTSP camera fleet
// (cam01..cam30, names from data/camera_registry.json), backed by the
// standalone scripts/live_camera_ai_service.py.
//
// On-demand by design: nothing is connected until a camera is picked from
// the dropdown below. Only the SELECTED camera's status is polled and only
// its raw/annotated streams are requested -- the backend opens that one
// real RTSP connection on the first request and releases it again once it
// stops being polled (e.g. after switching to a different camera). Nothing
// here is fabricated -- a camera that is OFFLINE/RECONNECTING is shown
// exactly as that, never swapped for another camera's feed or a demo clip.
export default function LiveCameraAIPage() {
  const [cameraOptions, setCameraOptions] = useState([]); // [{camera_id, name}]
  const [listLive, setListLive] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [camera, setCamera] = useState(null); // status of the selected camera
  const [cameraLive, setCameraLive] = useState(false);

  // Fetch the (id, name) list ONCE -- purely to populate the dropdown, no
  // camera connection is opened by this call.
  useEffect(() => {
    let cancelled = false;
    fetchLiveCameraList().then((res) => {
      if (cancelled) return;
      setCameraOptions(res.data.cameras.map((c) => ({ camera_id: c.camera_id, name: c.name })));
      setListLive(res.live);
    });
    return () => { cancelled = true; };
  }, []);

  // Poll ONLY the selected camera's status. This is what actually causes
  // the backend to open (and keep alive) that one real RTSP connection --
  // switching selection stops polling the old id, so it idles out and
  // disconnects server-side; nothing about any other camera is touched.
  useEffect(() => {
    if (!selectedId) { setCamera(null); return; }
    let cancelled = false;
    async function poll() {
      const res = await fetchCameraStatus(selectedId);
      if (cancelled) return;
      setCamera(res.data);
      setCameraLive(res.live);
    }
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [selectedId]);

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>Real-Time CCTV &amp; AI Detection</div>
        <div style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>
          {cameraOptions.length || "—"} real RTSP cameras available — pick one below. Only the selected camera is
          connected; nothing is loaded until you choose it. No demo or simulated data.
        </div>
      </div>

      {!listLive && (
        <Banner color={C.red} glow={C.redGlow}>
          Live Camera &amp; AI service unreachable — check scripts/live_camera_ai_service.py is running.
        </Banner>
      )}

      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <label style={{ color: C.muted, fontSize: 11.5 }}>Select Camera:</label>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          style={{
            background: C.panel, color: C.text, border: `1px solid ${C.border}`,
            borderRadius: 4, padding: "6px 12px", fontSize: 12.5, minWidth: 280,
          }}
        >
          <option value="">— choose a camera —</option>
          {cameraOptions.map((c) => (
            <option key={c.camera_id} value={c.camera_id}>{c.camera_id} — {c.name}</option>
          ))}
        </select>
      </div>

      {!selectedId ? (
        <div style={{
          background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8,
          padding: 40, textAlign: "center", color: C.muted, fontSize: 13,
        }}>
          No camera selected — pick one above to open its real live feed.
        </div>
      ) : (
        <CameraDetail camera={camera} cameraLive={cameraLive} cameraId={selectedId} />
      )}
    </div>
  );
}

function CameraDetail({ camera, cameraLive, cameraId }) {
  const camStatus = camera?.status || "OFFLINE";
  const camMeta = STATUS_STYLE[camStatus] || STATUS_STYLE.OFFLINE;
  const connected = camStatus !== "OFFLINE";
  const aiStatus = camera?.ai_status || "STARTING";
  const aiReady = connected && ["PROCESSING", "IDLE"].includes(aiStatus);

  return (
    <>
      {!cameraLive && (
        <Banner color={C.red} glow={C.redGlow}>
          Could not reach the Live Camera &amp; AI service for {cameraId}.
        </Banner>
      )}
      {cameraLive && !camera?.configured && (
        <Banner color={C.amber} glow={C.amberGlow}>
          {cameraId} has no RTSP URL configured in data/camera_registry.json.
        </Banner>
      )}

      <Section
        title="Provided Data / Live Camera"
        subtitle={`Real, unmodified feed from ${camera?.name || cameraId} — opened on demand for this selection`}
      >
        <FeedPanel
          streamUrl={rawStreamUrl(cameraId)}
          connected={connected}
          camStatus={camStatus}
          camMeta={camMeta}
          badge={{ text: "REAL FEED", color: C.green }}
        />
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: C.muted }}>
          <Metric label="Camera" value={`${cameraId} — ${camera?.name || "—"}`} />
          <Metric label="Status" value={camMeta.label} valueColor={camMeta.c} />
          <Metric label="Reconnects" value={camera?.reconnect_count ?? "—"} />
          <Metric label="Last Frame" value={camera?.last_frame_at ? new Date(camera.last_frame_at * 1000).toLocaleTimeString("en-IN", { hour12: false }) : "—"} />
        </div>
      </Section>

      <Section
        title="AI Vehicle Detection"
        subtitle="Real YOLO inference on this camera's live feed"
      >
        <FeedPanel
          streamUrl={annotatedStreamUrl(cameraId)}
          connected={aiReady}
          camStatus={aiReady ? camStatus : aiStatus}
          camMeta={aiReady ? camMeta : { c: C.muted, label: aiStatus }}
          badge={{ text: "AI ANNOTATED", color: C.violet }}
        />
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: C.muted }}>
          <Metric label="AI Status" value={aiStatus} valueColor={aiStatus === "PROCESSING" ? C.green : C.muted} />
          <Metric label="Model" value="YOLOv8 (ai/detection/vehicle_detector.py)" />
          <Metric label="Vehicles Detected" value={camera?.vehicles_detected ?? 0} valueColor={C.text} />
          {camera?.ai_model_error && <Metric label="Model Error" value={camera.ai_model_error} valueColor={C.red} />}
        </div>
        <DetectionsList detections={camera?.detections || []} />
      </Section>
    </>
  );
}

function FeedPanel({ streamUrl, connected, camStatus, camMeta, badge, height = 400 }) {
  const [imgError, setImgError] = useState(false);
  const imgRef = useRef(null);
  const openUrlRef = useRef(null);
  const streamUrlRef = useRef(streamUrl);
  const retryTimerRef = useRef(null);
  streamUrlRef.current = streamUrl;

  // A live MJPEG (multipart/x-mixed-replace) request never completes on its
  // own -- the browser holds it open for as long as the <img> keeps it.
  // React's per-origin HTTP/1.1 connection pool is shared across every tab
  // (default 6), so an <img> that gets swapped out via a changing `key`
  // (remounted, relying on garbage collection to eventually abort the old
  // request) can leak an open connection indefinitely -- a couple of leaks
  // and every further camera, in any tab, gets stuck pending forever. To
  // avoid that entirely, this ONE <img> node is never remounted: its `src`
  // is set/cleared imperatively, and cleanup always explicitly empties
  // `.src` first, which is the reliable way to make the browser abort an
  // in-flight request.
  const connectNow = () => {
    const img = imgRef.current;
    if (!img) return;
    const url = `${streamUrlRef.current}${streamUrlRef.current.includes("?") ? "&" : "?"}t=${Date.now()}`;
    img.src = url;
    openUrlRef.current = url;
    setImgError(false);
  };

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    if (!connected) {
      if (openUrlRef.current) { img.src = ""; openUrlRef.current = null; }
      return;
    }
    connectNow();
    return () => {
      if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
      img.src = "";
      openUrlRef.current = null;
    };
  }, [streamUrl, connected]);

  // A transient stream hiccup (the individual MJPEG connection erroring out
  // while the camera itself is still reported connected) gets one bounded
  // retry rather than sitting dead until something else changes.
  function handleImgError() {
    setImgError(true);
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = setTimeout(() => {
      if (imgRef.current && openUrlRef.current) connectNow();
    }, 3000);
  }

  const showImage = connected && !imgError;

  return (
    <div style={{
      position: "relative", background: "#000", borderRadius: 8, overflow: "hidden",
      height, display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{ position: "absolute", top: 8, left: 8, zIndex: 3, display: "flex", gap: 6 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,0.6)",
          color: camMeta.c, border: `1px solid ${camMeta.c}`, borderRadius: 3,
          padding: "2px 8px", fontSize: 10, fontWeight: 800, letterSpacing: 0.8,
        }}>
          {camStatus === "ONLINE" && <span style={{ width: 6, height: 6, borderRadius: "50%", background: camMeta.c }} />}
          {camMeta.label}
        </span>
        {showImage && (
          <span style={{
            background: "rgba(0,0,0,0.6)", color: badge.color, border: `1px solid ${badge.color}`,
            borderRadius: 3, padding: "2px 6px", fontSize: 8, fontWeight: 700,
          }}>
            {badge.text}
          </span>
        )}
      </div>

      {/* Always mounted (never keyed/remounted) so the effect above is the
          only thing that ever opens or closes its connection. */}
      <img
        ref={imgRef}
        alt="Live camera stream"
        onError={handleImgError}
        style={{ width: "100%", height: "100%", objectFit: "contain", display: showImage ? "block" : "none" }}
      />
      {!showImage && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: C.muted }}>
          <VideoOff size={22} />
          <div style={{ fontSize: 11 }}>
            {connected ? "Stream unavailable — retrying" : `${camMeta.label} — no live feed`}
          </div>
        </div>
      )}
    </div>
  );
}

function DetectionsList({ detections }) {
  if (!detections.length) {
    return (
      <div style={{ marginTop: 12, color: C.muted, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
        <Car size={13} /> No vehicles currently detected.
      </div>
    );
  }
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {detections.map((d, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 6, background: C.panel,
            border: `1px solid ${C.border}`, borderRadius: 4, padding: "4px 10px", fontSize: 11.5,
          }}>
            <Car size={12} color={C.accent} />
            <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{d.class}</span>
            <span style={{ color: C.muted }}>{(d.confidence * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Section({ title, subtitle, children }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 13 }}>{title}</div>
        <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{subtitle}</div>
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value, valueColor }) {
  return (
    <div>
      <div style={{ textTransform: "uppercase", letterSpacing: 0.6, fontSize: 9.5 }}>{label}</div>
      <div style={{ color: valueColor || C.text, fontWeight: 600, fontSize: 12.5, marginTop: 2 }}>{value}</div>
    </div>
  );
}

function Banner({ color, glow, children }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, background: glow,
      border: `1px solid ${color}`, color, borderRadius: 6,
      padding: "8px 12px", fontSize: 12, marginBottom: 14,
    }}>
      <AlertTriangle size={14} /> {children}
    </div>
  );
}
