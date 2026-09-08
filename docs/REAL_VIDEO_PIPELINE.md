# Real CCTV Video Pipeline (Phase 15A)

The camera → backend → frontend video path, and an **honest** playback
experience: a snapshot is never presented as a live feed.

---

## 1. Source model

`cameras` gains two nullable columns (migration `0012`):

| Column | Meaning |
| :--- | :--- |
| `webrtc_url` | WHEP (WebRTC) playback URL — low latency, **preferred** |
| `hls_url` | HLS (`.m3u8`) playback URL — widely compatible fallback |

Both are populated by an operator (`PATCH /cameras/{id}`) or the registry
sync **when a media gateway is deployed in front of the RTSP feed**. RTSP
ingestion is unchanged — these are purely the browser-facing sources.

### Why a gateway

Browsers cannot open `rtsp://` and cannot send the Basic-auth a government
RTSP endpoint needs. The standard bridge is a small media server
(**MediaMTX** / RTSPtoWeb / Janus) co-deployed with the ingestion host:

```
rtsp://<gov-camera>  ──►  MediaMTX  ──┬──►  /whep/<cam>     (webrtc_url)
                                      └──►  /hls/<cam>.m3u8 (hls_url)
```

MediaMTX is a single static binary, no database, ~15 MB — not "new
infrastructure for complexity", it is the minimum required to show real
video in a browser. It is **not bundled** (feeds are down); the columns and
the whole frontend player are ready for it.

## 2. `CameraStreamService.profile(camera)`

Returns the ordered playable sources + an honest **mode**:

| mode | condition |
| :--- | :--- |
| `LIVE` | a real-time source (webrtc/hls) is configured, the camera is not marked OFFLINE, health telemetry is fresh (≤ 20 s) and FPS ≥ `STREAM_LOW_FPS` (8) |
| `DEGRADED` | a real-time source exists but telemetry is stale or FPS is low |
| `RECORDED` | no usable real-time source — a mock/simulated clip or a recent evidence snapshot is the best available |
| `OFFLINE` | the camera is offline and there is nothing playable |

Fallback order the player walks: **`webrtc` → `hls` → `recorded` clip
(`/cameras/{id}/mock-video`) → latest `snapshot`**.
`mode_reasons[]` explains any non-LIVE mode.

`GET /api/v1/cameras/{id}/stream` → `CameraStreamProfile` (JWT).

## 3. Frontend — `CameraPlayer`

`frontend/src/components/camera/CameraPlayer.jsx`:

- fetches the profile, walks the sources, and on each source failure falls
  through to the next automatically;
- **HLS** via `hls.js` (added dependency) with native-HLS fallback (Safari);
- **recorded clip** via `<video>` + a short-lived media ticket `?token=`;
- **WebRTC** attempts WHEP and, with no gateway reachable, falls through
  with a clear message;
- **snapshot** renders as `<img>` with a permanent **"LAST FRAME — NOT A
  LIVE FEED"** overlay;
- the top-left badge **always** shows the real mode (`LIVE` pulsing red /
  `DEGRADED` amber / `RECORDED` violet / `OFFLINE` grey), plus a
  `MOCK STREAM` chip for mock cameras;
- a reconnect button re-fetches the profile and restarts the source walk;
- fatal errors surface as a red strip with the reason.

Wired into `CameraModal` (replaces the old "stream renders here in
production" placeholder) with the required info panel: code, status,
location, FPS, last frame, last detection, AI status, coordinates.

## 4. What is real / demo / requires deployment

| | Status |
| :--- | :--- |
| Playback abstraction + mode resolution + fallback chain | **implemented + tested** (`test_camera_stream.py`, 10) |
| Frontend player (HLS, recorded clip, snapshot, reconnect, honest labels) | **implemented**, build-verified |
| Recorded clip for mock cameras (`mock-video`) | **works today** — this is the RECORDED source in the offline demo |
| WebRTC / HLS live playback | **ready** — needs `webrtc_url` / `hls_url` set + a media gateway reachable; not exercisable with feeds down |
| Real RTSP → browser | requires the gateway above on the ingestion host |

## 5. Config

`STREAM_LOW_FPS` (8.0) — the FPS below which a live source is `DEGRADED`.
