import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Video, VideoOff } from "lucide-react";
import { C } from "../../theme.js";
import { http } from "../../services/api.js";
import { currentMediaTicket, ensureMediaTicket } from "../../services/mediaTicket.js";

const MODE_STYLE = {
  LIVE: { c: C.red, t: "LIVE" },
  DEGRADED: { c: C.amber, t: "DEGRADED" },
  RECORDED: { c: C.violet, t: "RECORDED" },
  OFFLINE: { c: C.muted, t: "OFFLINE" },
};

// Phase 15A — honest camera playback. Walks the backend-resolved source
// list (webrtc → hls → recorded clip → snapshot), shows the real playback
// mode, reconnect state and meaningful errors. A snapshot is NEVER labelled
// as a live feed — the badge always reflects the actual `mode`.
export default function CameraPlayer({ cameraId, height = 260 }) {
  const [profile, setProfile] = useState(null);
  const [sourceIdx, setSourceIdx] = useState(0);
  const [status, setStatus] = useState("loading"); // loading | playing | error | offline
  const [err, setErr] = useState("");
  const [attempt, setAttempt] = useState(0);
  const videoRef = useRef(null);
  const hlsRef = useRef(null);

  async function loadProfile() {
    setStatus("loading");
    setErr("");
    try {
      ensureMediaTicket().catch(() => {});
      const { data } = await http.get(`/cameras/${cameraId}/stream`);
      setProfile(data);
      setSourceIdx(0);
      if (!data.sources.length) setStatus("offline");
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Could not load camera stream profile");
      setStatus("error");
    }
  }

  useEffect(() => { loadProfile(); /* eslint-disable-next-line */ }, [cameraId]);

  // attach the current source
  useEffect(() => {
    if (!profile || !profile.sources.length) return;
    const src = profile.sources[sourceIdx];
    if (!src) { setStatus("error"); setErr("All stream sources failed"); return; }

    const mt = () => currentMediaTicket() || "";
    const withAuth = (u) => (u.includes("?") ? `${u}&` : `${u}?`) + `token=${encodeURIComponent(mt())}`;
    let cancelled = false;
    setStatus("loading");
    setErr("");

    const fail = (why) => {
      if (cancelled) return;
      if (sourceIdx < profile.sources.length - 1) {
        setSourceIdx((i) => i + 1);
      } else {
        setStatus("error");
        setErr(why || `Source "${src.kind}" failed and no fallback remains`);
      }
    };

    const cleanupHls = () => { if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null; } };
    cleanupHls();

    if (src.kind === "snapshot") {
      setStatus("playing");
      return () => { cancelled = true; };
    }

    if (src.kind === "webrtc") {
      // WHEP needs a media gateway; without one, fall straight through.
      fail("WebRTC/WHEP source configured — a media gateway (e.g. MediaMTX) must be reachable");
      return () => { cancelled = true; };
    }

    const video = videoRef.current;
    if (!video) return () => { cancelled = true; };

    if (src.kind === "hls") {
      import("hls.js")
        .then(({ default: Hls }) => {
          if (cancelled) return;
          if (Hls.isSupported()) {
            const hls = new Hls({ lowLatencyMode: true, maxBufferLength: 10 });
            hlsRef.current = hls;
            hls.loadSource(src.url);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => { if (!cancelled) { video.play().catch(() => {}); setStatus("playing"); } });
            hls.on(Hls.Events.ERROR, (_e, d) => { if (d.fatal) fail(`HLS error: ${d.details}`); });
          } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
            video.src = src.url;
            video.addEventListener("loadedmetadata", () => { if (!cancelled) { video.play().catch(() => {}); setStatus("playing"); } });
            video.addEventListener("error", () => fail("HLS playback error"));
          } else {
            fail("This browser cannot play HLS");
          }
        })
        .catch(() => fail("hls.js failed to load"));
      return () => { cancelled = true; cleanupHls(); };
    }

    // recorded clip (mp4) — needs the ?token= query param
    video.src = withAuth(src.url);
    video.loop = true;
    const onOk = () => { if (!cancelled) { video.play().catch(() => {}); setStatus("playing"); } };
    const onErr = () => fail("Recorded clip could not be played");
    video.addEventListener("loadeddata", onOk);
    video.addEventListener("error", onErr);
    return () => {
      cancelled = true;
      video.removeEventListener("loadeddata", onOk);
      video.removeEventListener("error", onErr);
      cleanupHls();
    };
  }, [profile, sourceIdx, attempt]);

  if (!profile && status === "loading") {
    return <Shell height={height}><Loader2 className="spin" size={20} color={C.muted} /></Shell>;
  }
  if (status === "error" && !profile) {
    return <Shell height={height}><div style={{ color: C.red, fontSize: 12 }}>{err}</div></Shell>;
  }

  const m = MODE_STYLE[profile?.mode] || MODE_STYLE.OFFLINE;
  const src = profile?.sources?.[sourceIdx];

  return (
    <div style={{ position: "relative", background: "#000", borderRadius: 8, overflow: "hidden", height }}>
      {/* mode badge — ALWAYS reflects reality */}
      <div style={{ position: "absolute", top: 8, left: 8, zIndex: 3, display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,0.6)", color: m.c, border: `1px solid ${m.c}`, borderRadius: 3, padding: "2px 8px", fontSize: 10, fontWeight: 800, letterSpacing: 0.8 }}>
          {profile.mode === "LIVE" && <span style={{ width: 6, height: 6, borderRadius: "50%", background: m.c }} />}
          {m.t}
        </span>
        {profile.is_mock && (
          <span style={{ background: "rgba(0,0,0,0.6)", color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "2px 6px", fontSize: 8, fontWeight: 700 }}>
            MOCK STREAM
          </span>
        )}
        {src && (
          <span style={{ background: "rgba(0,0,0,0.5)", color: C.muted, borderRadius: 3, padding: "2px 6px", fontSize: 9 }}>
            {src.label}
          </span>
        )}
      </div>

      <button onClick={() => { setAttempt((a) => a + 1); loadProfile(); }}
        style={{ position: "absolute", top: 8, right: 8, zIndex: 3, background: "rgba(0,0,0,0.6)", border: `1px solid ${C.border}`, color: C.muted, borderRadius: 3, padding: 4, cursor: "pointer" }}
        title="Reconnect">
        <RefreshCw size={12} />
      </button>

      {status === "offline" || profile.mode === "OFFLINE" ? (
        <Shell height={height}>
          <VideoOff size={22} color={C.muted} />
          <div style={{ color: C.muted, fontSize: 11, marginTop: 8 }}>
            {profile.mode_reasons?.[0] || "No playable source"}
          </div>
        </Shell>
      ) : src?.kind === "snapshot" ? (
        <>
          <img src={withImgAuth(src.url)}
            alt="latest frame" style={{ width: "100%", height: "100%", objectFit: "contain" }}
            onError={() => { if (sourceIdx < profile.sources.length - 1) setSourceIdx((i) => i + 1); }} />
          <div style={{ position: "absolute", bottom: 8, left: 8, zIndex: 3, background: "rgba(0,0,0,0.65)", color: C.amber, borderRadius: 3, padding: "2px 8px", fontSize: 9, fontWeight: 700 }}>
            LAST FRAME — NOT A LIVE FEED
          </div>
        </>
      ) : (
        <video ref={videoRef} muted playsInline
          style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />
      )}

      {status === "loading" && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2 }}>
          <Loader2 className="spin" size={20} color={C.muted} />
        </div>
      )}
      {status === "error" && (
        <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, zIndex: 3, background: "rgba(140,20,20,0.85)", color: "#fff", fontSize: 10.5, padding: "5px 10px", display: "flex", alignItems: "center", gap: 6 }}>
          <AlertTriangle size={12} /> {err}
        </div>
      )}
    </div>
  );
}

function withImgAuth(u) {
  const t = currentMediaTicket() || "";
  return (u.includes("?") ? `${u}&` : `${u}?`) + `token=${encodeURIComponent(t)}`;
}

function Shell({ children, height }) {
  return (
    <div style={{ height, background: "#0b0f14", borderRadius: 8, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      {children}
    </div>
  );
}
