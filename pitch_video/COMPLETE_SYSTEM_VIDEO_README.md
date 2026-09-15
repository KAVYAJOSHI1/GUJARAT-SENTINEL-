# SENTINEL — Complete System Demo Video

## What this is

A genuine screen recording of the actual running SENTINEL application — every page, every workflow, real seeded demo data — recorded via Playwright browser automation against the live Docker stack (frontend on `localhost:3000`, backend on `localhost:8001`). Not Remotion, not an HTML simulation, not screenshots: a real browser was driven end to end and its screen was captured.

## Files in this delivery

| File | Purpose |
|---|---|
| `COMPLETE_SENTINEL_SYSTEM_DEMO.mp4` | The final video |
| `SENTINEL_COMPLETE_SYSTEM_VIDEO_VOICEOVER.docx` | Voiceover script, timestamp-matched to the MP4 |
| `COMPLETE_SYSTEM_VIDEO_TIMELINE.md` | Second-by-second timeline table |
| `COMPLETE_SYSTEM_COVERAGE_MATRIX.md` | Every feature classified: inspected / functional / populated / recorded |
| `COMPLETE_SYSTEM_VIDEO_README.md` | This file |

## Video specs

- **Resolution**: 1920×1080
- **FPS**: 30 (motion-interpolated from Playwright's native 25fps capture — see "Smooth playback" below)
- **Duration**: 6:59 (419.7s)
- **Container**: MP4 (H.264 video, converted from Playwright's native WebM capture via ffmpeg)
- See `COMPLETE_SYSTEM_VIDEO_TIMELINE.md` for the full second-by-second breakdown (generated from the real recorded run's own logged timestamps).

## How it was produced

1. **Inspection** — every frontend route, backend endpoint, and page component was read from source, then every route was actually visited in a logged-in browser session this same conversation, screenshotted, and checked for console errors, empty states, and broken data. Two real bugs were found and fixed in the process (see the main conversation history): a stale evidence-placeholder graphic leaking into Incident/Case evidence thumbnails, and an admin-login credential drift.
2. **Planning** — every discovered feature was classified A (must demonstrate) through D (skip, with a documented reason) in `COMPLETE_SYSTEM_COVERAGE_MATRIX.md`.
3. **Recording** — `frontend/_record_full_demo.mjs` (a Playwright script, not checked into the app itself) drives a real headless Chrome through every planned section in one continuous take: the Landing Page is scrolled smoothly end-to-end over ~65s riding the site's own Lenis easing (not fought with rapid small steps), login goes through the landing page's real inline sign-in form, and every other section uses eased mouse movement, deliberate holds, real typing, and real navigation. `context.recordVideo` captured the session natively; the script also logs the exact elapsed-time boundary of every section to `full_demo_timeline.json`.
4. **Smooth playback pass** — Playwright's native capture is 25fps; naively forcing it to 30fps with `ffmpeg -r 30` duplicates frames on a fixed cycle, which is what produced visible judder in an earlier draft. Fixed by converting with the `minterpolate=fps=30:mi_mode=blend` filter instead, which blends between real frames rather than repeating one — verified afterwards with a frame-by-frame pixel-diff scan showing no periodic duplicate pattern.
5. **Doc generation** — `generate_docs.py` reads that same JSON log (never hand-typed numbers) to produce the timeline markdown and the DOCX voiceover script, so both are guaranteed to match the actual video, not a plan.
6. **Verification** — the finished MP4 was sampled at multiple timestamps (including a frame-diff smoothness scan) and checked against the timeline for correctness before delivery.

## How to reproduce

```bash
# 1. Stack must be running (docker compose up -d) and seeded:
#    ./scripts/reset_demo.sh

# 2. Record (from frontend/, with ADMIN_USERNAME/ADMIN_PASSWORD in ../.env):
cd frontend
set -a && source ../.env && set +a
node _record_full_demo.mjs
# -> writes pitch_video/full_demo_raw/*.webm and pitch_video/full_demo_timeline.json

# 3. Convert to MP4 at a smooth 30fps (blend interpolation, not frame duplication):
ffmpeg -i pitch_video/full_demo_raw/<hash>.webm \
  -vf "minterpolate=fps=30:mi_mode=blend" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset faster \
  pitch_video/COMPLETE_SENTINEL_SYSTEM_DEMO.mp4

# 4. Regenerate the timeline + voiceover docs from the real recorded timestamps:
cd ../pitch_video
python3 generate_docs.py
```

## Routes covered

All 26 top-level frontend routes, plus the Camera Detail modal, the Ctrl+K command palette, and the AI Copilot / Investigation Graph / GIS journey interactions for the deterministic demo vehicle `GJ18TC0450`. Full per-feature breakdown in `COMPLETE_SYSTEM_COVERAGE_MATRIX.md`.

## Skipped features and why

Every skip is documented with a reason in `COMPLETE_SYSTEM_COVERAGE_MATRIX.md`. In summary: the Incidents/Cases *list* pages (grouped — same list→detail pattern already shown by Camera Network/Management), the standalone Evidence Modal and Notification dropdown (content duplicates what's already shown elsewhere in the video), the Alert Drawer (overlaps the Alert Log page), and destructive confirm-dialogs (detach evidence / deactivate watchlist) — deliberately not triggered on camera because they would mutate the shared seeded demo dataset.

## Real bugs found and fixed during production

This is worth stating plainly rather than burying: producing this video surfaced genuine, previously-unknown defects, not just recording-script issues.

1. **A real crash, fixed in the app.** `InvestigationPage.jsx`'s map used the chronologically-first sighting's coordinates unconditionally as the map's initial center. Because the demo's mock cameras have been running continuously for hours and some of their sightings carry no coordinates, an early take crashed Leaflet's `MapContainer` outright (`Cannot read properties of null (reading 'lat')`) the moment a plate search resolved. Fixed in `frontend/src/pages/InvestigationPage.jsx` to fall back to the first sighting that actually has coordinates.
2. **A recording-script bug that silently swapped a whole section's content.** The Vehicle Investigation Workspace and Global Search sections both used a generic `input.first()` / raw `Control+K` keypress that, on those two specific pages, resolved to the wrong element — the persistent navbar search box, and a keyboard listener that doesn't reliably fire under headless automation — silently showing the *Advanced Search* page instead of the intended content, with no error thrown. Caught only by manually reviewing extracted frames against the logged timeline, not by the "0 console errors" signal alone. Fixed by targeting each page's own labelled input and by clicking the visible Ctrl+K button instead of dispatching a raw keypress.
3. **Stale hardcoded IDs after a demo-data reseed.** The recording script's Incident Detail and Case Detail sections navigate directly to a fixed incident/case UUID. Between takes the demo database was reseeded, which assigns new UUIDs to the deterministic `INC-2026-9001` / `CASE-2026-9001` records — the old UUIDs pointed at rows that no longer existed, so those two sections silently rendered a "not found or backend unavailable" error for their full ~10s duration in one draft, with zero console errors and no thrown exception. Caught the same way as bug 2: by extracting and eyeballing frames at each section's timestamp rather than trusting the clean log. Fixed by re-querying `/api/v1/incidents` and `/api/v1/cases` for the current live UUIDs and updating the two constants at the top of `frontend/_record_full_demo.mjs`.
4. **Visible playback judder from naive fps conversion, not the app.** An early exported video felt laggy on scroll and playback generally. Root cause: Playwright records at a native 25fps, and converting that to 30fps with plain `ffmpeg -r 30` duplicates frames on a fixed cycle (roughly every 6th output frame is a repeat), which reads as periodic stutter — a post-processing artifact, not real browser or CPU jank. Fixed by re-encoding with `minterpolate=fps=30:mi_mode=blend` instead, and verified with a pixel-diff scan across the finished MP4 confirming the periodic-duplicate pattern is gone and any near-static stretches are genuine content holds, not encoding artifacts.

**Takeaway for anyone reproducing this**: a clean run with zero console errors is necessary but not sufficient — always spot-check actual frame content against what each section is supposed to show, not just the error log, and always sanity-check any hardcoded IDs against the current live database before recording.

## Known limitations

- The demo dataset is deterministic and Ahmedabad-scoped (8 real-coded cameras + 3 mock cameras); it is not a claim that Sentinel is deployed at that scale today — see the project's own `SUBMISSION_REQUIREMENTS.md` for the honest capability breakdown.
- The mock pipeline (`mockcam01-03`) ran continuously for several hours during this working session, generating hundreds of incidental real (not fabricated) watchlist-match detections for the demo plate `GJ18TC0450`. This is genuine system activity, not a bug, but it means the GIS Investigation Console section shows a much larger, messier sighting history (~200 sightings, several without coordinates) than the originally-designed clean 5-camera route, and its map legitimately reports "not enough geolocated sightings to draw a trail" for the full-history view — the Vehicle Investigation Workspace section's own map, shown moments earlier, does successfully plot a real route from the same data. Nothing here was hidden or faked; it's the system exactly as it stood at recording time.
- Video is silent — narration is recorded separately by the presenter using the provided DOCX script.
