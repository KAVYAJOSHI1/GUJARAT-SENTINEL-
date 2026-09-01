# DEVELOPER EXECUTION GUIDE — ISHA

## 1. Developer Details
- **Developer Name**: Isha
- **Role**: Frontend Lead & Main Command Dashboard Engineer
- **Git Branch**: `feature/isha-frontend`

---

## 2. Mission
Isha is responsible for building the React.js single-page web command center dashboard for the SENTINEL platform. The interface must provide real-time operational visibility across 50+ CCTV camera streams, display system-wide KPI metrics, render live video previews, list recent watchlist events, and present sub-second alert toasts received via WebSockets from the backend engine.

---

## 3. Exact Features Owned
- **Command Dashboard (`/`)**: Key performance metrics (Total Cameras, Online Streams, Active Alerts, Today's Detections).
- **Navigation Bar**: Persistent header with active route highlighting, system health status, and alert indicators.
- **Live Camera Grid (`/cameras`)**: 2x2 and 3x3 video stream preview players with status badges and metadata overlays.
- **Alert Panel**: Slide-over drawer displaying critical watchlist alerts with an "Acknowledge" action button.
- **Real-Time WebSocket Toast Notifications**: Instant audio/visual alert toasts triggered upon receiving websocket alert payloads.
- **UI States**: Skeleton loading states, empty data states, API connection error banners, and offline badges.

---

## 4. Files You Should Work On
```text
frontend/
├── src/
│   ├── components/
│   │   ├── Navbar.jsx
│   │   ├── StatCard.jsx
│   │   ├── CameraGrid.jsx
│   │   ├── AlertFeed.jsx
│   │   └── LiveStreamPlayer.jsx
│   ├── pages/
│   │   ├── Dashboard.jsx
│   │   ├── CamerasPage.jsx
│   │   └── AlertsPage.jsx
│   ├── services/
│   │   ├── api.js
│   │   └── websocket.js
│   ├── styles/
│   │   └── index.css
│   ├── App.jsx
│   └── main.jsx
├── package.json
└── README.md
```

---

## 5. Technologies
- **Framework**: React 18+ (bootstrapped with Vite)
- **Styling**: Vanilla CSS3 / CSS Modules (Dark Glassmorphism palette)
- **Icons**: Lucide-React (`lucide-react`)
- **HTTP / WebSockets**: Axios, Native Browser WebSocket API

---

## 6. Input
- **Dashboard Stats REST API**: `GET /api/v1/dashboard/stats`
- **Cameras REST API**: `GET /api/v1/cameras`
- **Alerts REST API**: `GET /api/v1/alerts/recent`
- **Live WebSocket Feed**: `ws://localhost:8000/ws/alerts`

---

## 7. Processing Pipeline
```text
1. App Launch ──► Mount Navigation Bar & Initialize Axios Client
2. Mount Dashboard ──► Parallel Fetch (/stats, /cameras, /alerts) ──► Populate Metric Widgets
3. Open WebSocket Connection ──► Listen on ws://localhost:8000/ws/alerts
4. On WS Message Received ──► Append Alert to State ──► Trigger Notification Toast
5. User Clicks Acknowledge ──► POST /api/v1/alerts/{id}/acknowledge ──► Update UI Badge
```

---

## 8. Output
- Fully interactive React single-page command center web application running on port `3000` / `5173`.
- HTTP POST request payloads acknowledging watchlist alerts.

---

## 9. API Contract Reference
All API requests and responses must strictly comply with **`docs/API_CONTRACTS.md`**:
- **Camera Schema**: `docs/API_CONTRACTS.md#1-camera-object-schema`
- **Alert Schema**: `docs/API_CONTRACTS.md#3-alert-object-schema`
- **Standard Errors**: `docs/API_CONTRACTS.md#6-standardized-http-api-error-response-format`

---

## 10. Integration Dependencies
- **Upstream Providers**:
  - **Vanshal (`feature/vanshal-backend`)**: Provides REST endpoints (`/stats`, `/cameras`, `/alerts`) and WebSocket server (`/ws/alerts`).
  - **Rishit (`feature/rishit-stream`)**: Provides HLS / WebRTC stream preview links for video playback components.
- **Downstream Consumers**:
  - **Vishakha (`feature/vishakha-investigation`)**: Links from dashboard camera cards directly into Vishakha's GIS Map & Investigation console.

---

## 11. Testing Requirements
- Execute component unit tests: `npm run test`
- Test API error states by mocking HTTP 500 responses with Axios mock adapters.
- Test WebSocket reconnection UI behavior by temporarily stopping backend socket server.

---

## 12. Definition of Done (DoD)
- [ ] Application compiles cleanly with zero ESLint or build errors (`npm run build`).
- [ ] Stat metrics dynamically populate from `/api/v1/dashboard/stats`.
- [ ] WebSocket alerts render instant toast popups on the dashboard screen.
- [ ] All UI components adhere to dark-mode glassmorphism styling tokens.
- [ ] Code committed to `feature/isha-frontend` and Pull Request opened to `testing`.

---

## 13. Git Branching Instructions
```bash
# 1. Work exclusively on your feature branch
git checkout feature/isha-frontend

# 2. Commit changes
git add .
git commit -m "feat(frontend): build main command dashboard and websocket alert toasts"

# 3. Push to GitHub
git push origin feature/isha-frontend

# 4. Open Pull Request on GitHub:
# feature/isha-frontend  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```
