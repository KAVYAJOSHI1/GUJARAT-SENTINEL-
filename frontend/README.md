# SENTINEL — Frontend (Command Center)

Owner: **Isha** · Branch: `feature/isha-frontend`
React 18 + Vite. Client-side command dashboard for the Gujarat Police CCTV
Integration & Video Analytics platform.

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000  (proxies /api and /ws to :8000)
npm run build      # -> dist/
npm run preview    # serve the production build
```

The UI runs with **no backend**: if `GET /api/v1/*` fails it falls back to
`src/lib/mockData.js`, and if the alert WebSocket can't connect it drives a
local alert simulator so real-time toasts still demo.

## Routes

| Path             | Owner    | Contents                                            |
| ---------------- | -------- | -------------------------------------------------- |
| `/`              | Isha     | Command dashboard — KPIs, camera grid, alert feed  |
| `/cameras`       | Isha     | Full camera network + zone filters + details modal |
| `/alerts`        | Isha     | Alert log + severity filters + acknowledge         |
| `/investigation` | Vishakha | GIS map + vehicle investigation (placeholder here) |
| `/map`           | Vishakha | Leaflet map (placeholder here)                     |

`/investigation` and `/map` render `pages/InvestigationPlaceholder.jsx` until
Vishakha's `feature/vishakha-investigation` branch adds `pages/InvestigationPage.jsx`
and `components/gis/`. Do not build GIS / vehicle-history UI in this branch.

## Backend contract

Endpoints and payload shapes follow `docs/API_CONTRACTS.md` on `testing`
(not present in this workspace). `src/services/api.js` normalises the most
likely field spellings so real and mock payloads are interchangeable — tighten
`normalizeCamera` / `normalizeAlert` once the contract file is available.
