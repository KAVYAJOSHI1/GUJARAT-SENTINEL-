# SENTINEL — Pitch Video (Remotion)

A real, rendered 75-second `.mp4` — not an HTML simulation — built with
[Remotion](https://remotion.dev) (React → video, frame-by-frame, via headless
Chrome + ffmpeg). Silent by design: voiceover is added afterward, timed
against `../PITCH_VIDEO_SCRIPT.md`.

**Output**: `out/sentinel-pitch.mp4` — 1920×1080, 30fps, 2250 frames, ~2.6MB, no audio track.

## Brand source of truth

Every color/font/copy choice here is pulled from the actual product, not
invented:

- `src/theme.js` — ported 1:1 from `frontend/src/styles/index.css`'s
  `.hp-root` block (the real Orqis landing-page palette: ivory `#f5f0e8` text,
  teal `#5ecfb8` accent, deep viridian-black ground) and `frontend/src/theme.js`'s
  `C` object (real amber/red/green status semantics, used only for
  alert/status indicators, never as the brand accent).
- Fonts: Anton (display), DM Mono (technical labels), Inter (body) — the
  exact three faces `.hp-root` declares.
- `public/logo.png` — the real Gujarat Police crest, copied from
  `frontend/public/gujarat-police-logo.png`.
- Copy in Scene 7 ("EVERY CITY HAS EYES. SENTINEL MAKES THEM THINK.", the
  subhead, the eyebrow) is lifted verbatim from `frontend/src/components/home/Hero.jsx`.
- All camera codes/names in the Scene 4 hero journey (CAM-01 Paldi Circle →
  CAM-02 Nehru Bridge West → CAM-04 Income Tax Circle → CAM-06 Vijay Cross
  Road → CAM-08 Ranip Cross Road), the plate `GJ18TC0450`, `CASE-2026-9001`,
  and the Scene 6 stat row (8 cameras live / 93% ANPR confidence / <1s alert
  latency / 0 hallucinated plates) are the **real seeded demo values** from
  `scripts/seed_ai_demo.py` and the Home page's own HUD cards — never
  invented, and never the mockup screenshots' invented statewide numbers
  (2,240 cameras etc.), which were deliberately excluded per the brief.

## Structure

```
src/
  index.jsx        entry — loads Google Fonts, registers the root
  Root.jsx          <Composition> definition (id "Sentinel", 2250f @ 30fps, 1920x1080)
  Video.jsx         assembles all 8 scenes via <Series>, owns the frame budget
  theme.js          color/type tokens + REAL_DEMO data constants
  components/
    Backdrop.jsx     shared ground gradient + film-grain overlay
    SceneShell.jsx   per-scene fade-in/out wrapper
    Text.jsx         Headline / MonoLabel / Body primitives
  scenes/
    Scene1Problem.jsx        camera-grid hook
    Scene2ProblemDetail.jsx  10 cameras / 10 minutes / 0 people stat reveal
    Scene3Reveal.jsx         logo reveal + camera→AI→plate→match pipeline
    Scene4Journey.jsx        HERO — cross-camera journey map + USP lines
    Scene5Workflow.jsx       Alert→Investigation→Case→Report chain
    Scene6Proof.jsx          credibility beat, real stats only
    Scene7Landing.jsx        cinematic push-in on the real Hero copy
    Scene8Close.jsx          logo lockup + final tagline
public/logo.png     the real Gujarat Police crest
```

Scene durations live in one place — `DURATIONS` in `src/Video.jsx` — and
must stay in sync with the timing table in `../PITCH_VIDEO_SCRIPT.md` if
ever changed.

## Rendering

This machine already has everything needed — no downloads required:

```bash
cd pitch_video
npm install   # first time only

# ffmpeg: Remotion shells out to a binary literally named `ffmpeg` on PATH.
# This host doesn't have system ffmpeg, but a real one ships inside the
# Playwright browser cache — point PATH at it (a symlink named `ffmpeg`
# pointing at `ffmpeg-linux` was created there so this resolves):
export PATH="$HOME/.cache/ms-playwright/ffmpeg-1011:$PATH"

# Chrome: modern Chrome removed old-style headless mode, which Remotion's
# renderer needs. Use the standalone chrome-headless-shell Playwright also
# cached, via the config's SENTINEL_CHROME_PATH hook:
SENTINEL_CHROME_PATH="$HOME/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell" \
  npx remotion render src/index.jsx Sentinel out/sentinel-pitch.mp4
```

`npm start` opens the Remotion Studio (live preview/scrub UI) if you want to
tweak timing visually instead of re-rendering blind — it uses a normal
browser tab, no special Chrome path needed for preview, only for the final
`render` command.

### Two non-obvious fixes baked into this repo already

1. `remotion.config.js` imports `Config` from `@remotion/cli/config`, not
   `remotion/config` — the latter doesn't exist in Remotion v4's export map.
2. `src/index.jsx` calls `loadFont("normal", options)` — the
   `@remotion/google-fonts` helpers take the style as the *first* positional
   argument, not inside the options object.

## Editing the film

- Change wording/timing → edit the relevant `scenes/SceneN*.jsx` file and/or
  `DURATIONS` in `Video.jsx`.
- Change the palette → edit `src/theme.js` only; every scene reads from it.
- Add real product footage → this project intentionally has **no screen
  recordings**; the ~2-3s "product teaser" (Scene 7) is a faithful
  re-render of the real Hero component, not a screenshot, per the brief
  ("no scrolling, no feature tour"). The full product walkthrough is a
  separate Playwright-recorded video, not this one.
