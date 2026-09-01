# Implementation Specification — ISHA (Frontend & Main Dashboard)

---

### 1. Ownership
- **Developer Name**: Isha
- **Module Ownership**: React Frontend Architecture & Main Command Dashboard
- **Git Branch**: `feature/isha-frontend`

---

### 2. Objective
Build an intuitive React single-page command dashboard that provides real-time visualization of camera feeds, system metrics, watchlist alert popups, and navigation across the SENTINEL platform.

---

### 3. Responsibilities
- Architect the React component tree and state management.
- Implement dashboard metric widgets (Total Cameras, Online Streams, Active Alerts, Today's Detections).
- Build the live camera grid player supporting HLS/video fallback playback.
- Implement real-time WebSocket alert listener for instant toast notifications.
- Ensure premium dark-mode aesthetics with responsive CSS layouts.

---

### 4. Features to Implement
1. **Command Center Overview (`/`)**: Real-time KPI counters, recent alert list, and system health status.
2. **Live Camera Grid (`/cameras`)**: 2x2 and 3x3 video stream grids with camera metadata overlays.
3. **Watchlist Alert Drawer**: Slide-over alert list with "Acknowledge" action button.
4. **Navigation Header**: Top navigation bar with active route highlighting and status indicators.

---

### 5. Module Architecture
```text
React App (App.jsx)
 ├── Navigation Bar (Navbar.jsx)
 ├── Routes Handler
 │    ├── Dashboard Page (Dashboard.jsx)
 │    │    ├── Stat Metrics Grid (StatCard.jsx)
 │    │    ├── Recent Alert Feed (AlertFeed.jsx)
 │    │    └── Quick Camera Grid (CameraGrid.jsx)
 │    ├── Cameras Page (CamerasPage.jsx)
 │    │    └── Video Stream Player (LiveStreamPlayer.jsx)
 │    └── Alert Center Page (AlertsPage.jsx)
 └── Services Layer
      ├── API Axios Client (api.js)
      └── WebSocket Alert Listener (websocket.js)
```

---

### 6. Technologies
- **Framework**: React.js (Vite)
- **Styling**: Vanilla CSS3 / CSS Modules (Dark Glassmorphism palette)
- **Icons**: Lucide-React
- **HTTP/Sockets**: Axios, Native WebSocket API

---

### 7. Folder Structure
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

### 8. Detailed Implementation Tasks
1. Initialize React project scaffolding with Vite.
2. Create CSS custom properties for color tokens (Dark Navy `#0A0F1D`, Card Glass `rgba(16, 24, 40, 0.75)`, Accent Blue `#2563EB`, Critical Red `#EF4444`).
3. Build `Navbar.jsx` with active route navigation links.
4. Build `StatCard.jsx` component supporting numerical values, trend percentages, and icons.
5. Create Axios HTTP wrapper (`api.js`) for fetching `/api/v1/dashboard/stats`, `/api/v1/cameras`, and `/api/v1/alerts`.
6. Implement `websocket.js` listener connecting to `ws://localhost:8000/ws/alerts` that appends incoming alerts to global state and triggers browser audio/visual notifications.
7. Build `LiveStreamPlayer.jsx` using HTML5 video tags for HLS/MP4 preview streams with fallback placeholder state when stream is offline.
8. Implement UI state handling: Loading Spinner, Empty Data state, API Error Banner, Offline Indicator.

---

### 9. Input
- REST API JSON responses from Vanshal's backend.
- WebSocket alert JSON payloads from Vanshal's backend dispatcher.

---

### 10. Output
- Rendered interactive web user interface in the browser.
- HTTP POST request payloads for alert acknowledgments.

---

### 11. APIs Consumed
- `GET /api/v1/dashboard/stats`: Returns dashboard summary counters.
- `GET /api/v1/cameras`: Returns array of registered camera objects.
- `GET /api/v1/alerts/recent`: Returns list of latest watchlist alerts.
- `POST /api/v1/alerts/{id}/acknowledge`: Updates alert acknowledgment status.
- `WS /ws/alerts`: WebSocket live stream for critical alerts.

---

### 12. Database Interaction
No direct database access. All data interactions occur strictly via backend REST endpoints and WebSockets.

---

### 13. Dependencies on Other Members
- **Vanshal**: Requires backend API endpoints (`/stats`, `/cameras`, `/alerts`) and WebSocket server.
- **Rishit**: Requires valid HLS/WebRTC URLs for video playback.

---

### 14. Integration Contract
Must adhere to `docs/API_CONTRACTS.md` for Alert and Camera object schemas.

---

### 15. Error Handling & UI States
- **Loading State**: Displays skeleton loading cards while API requests are pending.
- **Empty State**: Displays clear "No Recent Alerts" illustration when alert list is empty.
- **Error State**: Displays red banner with retry button if backend is unreachable.
- **WebSocket Disconnect State**: Displays "Reconnecting to Alert Engine..." badge in top navbar.

---

### 16. Testing Requirements
- Unit test `StatCard.jsx` using Jest / React Testing Library.
- Mock API responses with Axios-mock-adapter to test loading and error states.

---

### 17. Performance Requirements
- Initial dashboard load time $< 1.5$ seconds.
- WebSocket alert render latency $< 100$ ms after packet receipt.

---

### 18. Day 1 Plan
Scaffolding Vite React app, top navigation, layout components, and CSS color tokens.

---

### 19. Day 2 Plan
Implement Dashboard stat cards, Recent Alert Feed component, and Axios API service integration.

---

### 20. Day 3 Plan
Build Live Camera Grid with `LiveStreamPlayer.jsx` and integrate WebSocket alert notification listener.

---

### 21. Day 4 Plan
UI polish, dark mode glassmorphism styling harmonization, and integration validation against `testing` branch.

---

### 22. Definition of Done (DoD)
- [ ] React application builds cleanly with `npm run build` without warnings.
- [ ] Dashboard stat cards dynamically populate from `/api/v1/dashboard/stats`.
- [ ] WebSocket alerts trigger visible popups on the dashboard.
- [ ] Code committed to `feature/isha-frontend` and verified on `testing`.

---

### 23. Deliverables
- Complete `frontend/` source codebase.
- User interface component documentation.

---

### 24. What NOT to do
- Do NOT hardcode API URLs without reading from environment variables (`import.meta.env.VITE_API_URL`).
- Do NOT make direct SQL or database queries from the frontend.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] Tested locally with backend running
- [ ] No hardcoded secrets committed
- [ ] Environment variable blueprint updated
- [ ] PR opened from `feature/isha-frontend` to `testing`
