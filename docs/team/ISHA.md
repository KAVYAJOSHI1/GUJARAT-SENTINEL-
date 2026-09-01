# Team Specification — ISHA

## 1. Developer Profile & Module Ownership
- **Member Name**: Isha
- **Module Ownership**: Frontend + Main Command Dashboard
- **Git Branch**: `feature/isha-frontend`

---

## 2. Core Responsibilities
- Architect and develop the React single-page dashboard application.
- Build the main command overview page, navigation, live camera preview grids, real-time alert cards, and status metrics.
- Integrate REST APIs and WebSocket / Server-Sent Events (SSE) from Vanshal's backend for real-time alert popups.
- Ensure dark mode aesthetic, smooth CSS transitions, and high-performance UI responsiveness.

---

## 3. UI Screens & Features to Implement
1. **Main Command Dashboard (`/`)**: High-level KPIs (Total Cameras, Online Streams, Active Watchlist Alerts, Detections Today), camera feed grid, recent alert feed.
2. **Live Camera Grid (`/cameras`)**: Multi-camera grid (2x2, 3x3) displaying live WebRTC/HLS video feeds with overlay metadata.
3. **Alert Center (`/alerts`)**: Categorized alert list (Critical, High, Medium) with quick action buttons (Acknowledge, Investigate, View Evidence).
4. **Camera Registry View (`/registry`)**: Tabular list of onboarded cameras, online/offline indicators, stream URLs, and department tags.

---

## 4. Technology Stack
- **Framework**: React.js (Vite / CRA)
- **Styling**: Vanilla CSS3 / CSS Modules / Modern UI tokens (Dark Glassmorphism)
- **Icons & Visuals**: Lucide-React / FontAwesome
- **HTTP & Sockets**: Axios, Native WebSocket API

---

## 5. Interface & Data Contracts

### 5.1 APIs Consumed
- `GET /api/v1/dashboard/stats`: Summary counts of cameras, alerts, and detections.
- `GET /api/v1/cameras`: List of all onboarded cameras and live stream URLs.
- `GET /api/v1/alerts/recent`: Fetch latest watchlist alerts.
- `POST /api/v1/alerts/{id}/acknowledge`: Mark an alert as reviewed.
- `WS ws://localhost:8000/ws/alerts`: Live alert notification stream.

### 5.2 Inputs & Outputs
- **Input**: REST JSON responses from Backend, WebSocket alert payloads.
- **Output**: User trigger events (e.g. alert acknowledgment, camera filter switches).

---

## 6. Expected Directory Layout (`frontend/`)
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
│   │   ├── AlertsPage.jsx
│   │   └── RegistryPage.jsx
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

## 7. Development Priorities
1. **Day 1**: Scaffolding React project, top nav, main layout, mock stat cards.
2. **Day 2**: Implement Camera Grid component with HLS/video fallback players.
3. **Day 3**: Connect real-time WebSocket alert listener & alert cards.
4. **Day 4**: UI polish, dark theme harmonization, testing with live backend endpoints.

---

## 8. Definition of Done (DoD) & Testing Requirements
- [ ] React dashboard builds cleanly with zero console errors.
- [ ] Stat metrics dynamically update from backend `/stats` endpoint.
- [ ] WebRTC/HLS video streams render without UI freeze.
- [ ] WebSocket alerts trigger an audible/visual toast notification immediately upon publish.
- [ ] Code committed to `feature/isha-frontend` and tested against `testing` branch.

---

## 9. Inter-Member Dependencies
- **Vanshal**: Requires backend REST endpoints for stats, alerts, and camera catalogue.
- **Rishit**: Requires live stream URLs (HLS/WebRTC) for camera playback grid.
