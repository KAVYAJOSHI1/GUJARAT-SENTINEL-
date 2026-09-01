# DEVELOPER EXECUTION GUIDE — ISHA

---

### 1. Developer Details
- **Developer Name**: Isha
- **Role**: Frontend Lead & Main Command Dashboard Engineer
- **Git Branch**: `feature/isha-frontend`

---

### 2. Project Objective
Build the React.js web application command center for the **SENTINEL** Gujarat Police CCTV Integration & Video Analytics Platform. Provide real-time visibility across 50+ camera streams, render system metrics, display live stream grid previews, list recent watchlist detections, and present sub-second alert toasts via WebSockets.

---

### 3. Exact Responsibility
You own the client-side user interface (`frontend/`). You are responsible for creating the main command dashboard, top navigation, KPI summary cards, live camera grid layout, alert drawer, real-time toast notification engine, API integration service, loading skeletons, error banners, and responsive layout.

---

### 4. Exact Features to Build
1. **Command Center Dashboard (`/`)**: Metric cards (Total Cameras, Online Feeds, Active Alerts, Today's Detections).
2. **Navigation Header**: Persistent header displaying system status, clock, and active view tabs.
3. **Live Camera Grid (`/cameras`)**: 2x2 and 3x3 video preview cards with status badges and metadata overlays.
4. **Alert Panel & Drawer (`/alerts`)**: Slide-over drawer detailing watchlist alerts with an "Acknowledge" button.
5. **Real-Time WebSocket Toast Engine**: Visual and acoustic popups triggered immediately upon receiving alert messages over WebSockets.
6. **Camera Details Modal**: Modal view displaying stream resolution, FPS, protocol (RTSP/WebRTC), and location details.
7. **UI States**: Skeleton loaders, empty data placeholders, connection error banners, and offline indicators.

---

### 5. What NOT to Build
- Do NOT build backend API routes or database models (owned by Vanshal).
- Do NOT build GIS map polyline trajectory renderers or vehicle search history (owned by Vishakha).
- Do NOT build AI inference, YOLO, or OCR logic (owned by Kavya).
- Do NOT build stream ingestion worker pools or RTSP decoders (owned by Rishit).

---

### 6. Technologies
- **Core Stack**: React 18+ (bootstrapped with Vite)
- **Styling**: Vanilla CSS3 / CSS Modules (Dark Glassmorphism UI tokens)
- **Icons**: Lucide-React (`lucide-react`)
- **HTTP / Sockets**: Axios, Native Browser WebSocket API

---

### 7. Recommended Models / Libraries
- `vite` & `@vitejs/plugin-react`
- `lucide-react`
- `axios`
- `clsx` / `tailwind-merge` (optional utility helpers)

---

### 8. Input
- **Dashboard Stats Endpoint**: `GET /api/v1/dashboard/stats`
- **Cameras Inventory Endpoint**: `GET /api/v1/cameras`
- **Recent Alerts Endpoint**: `GET /api/v1/alerts/recent`
- **Live WebSocket Feed**: `ws://localhost:8000/ws/alerts`

---

### 9. Processing Pipeline
```text
1. Mount Application ──► Initialize Navigation & Axios API Client
2. Mount Dashboard ──► Concurrent Fetch (/stats, /cameras, /alerts) ──► Render Metric Cards
3. Open WebSocket Connection ──► Listen on ws://localhost:8000/ws/alerts
4. On WS Event Received ──► Append Alert to Feed State ──► Trigger Toast Popup
5. Click "Acknowledge" ──► POST /api/v1/alerts/{id}/acknowledge ──► Update UI Badge State
```

---

### 10. Output
- React single-page web application compiled to `dist/` running on dev server `http://localhost:3000`.
- User interactions dispatching POST HTTP requests to acknowledge alerts.

---

### 11. Required API Contract
Must strictly adhere to `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **Camera Schema**: `docs/API_CONTRACTS.md#1-camera-object-schema`
- **Alert Schema**: `docs/API_CONTRACTS.md#3-alert-object-schema`
- **Error Response**: `docs/API_CONTRACTS.md#6-standardized-http-api-error-response-format`

---

### 12. Database Interaction
No direct database interaction. All data reads/writes must pass through Vanshal's FastAPI backend REST endpoints.

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - **Vanshal (`feature/vanshal-backend`)**: Supplies REST endpoints (`/stats`, `/cameras`, `/alerts`) and WebSocket server (`/ws/alerts`).
  - **Rishit (`feature/rishit-stream`)**: Supplies HLS / WebRTC stream preview links for video playback components.
- **Downstream Consumers**:
  - **Vishakha (`feature/vishakha-investigation`)**: Links from camera preview cards directly into Vishakha's GIS Map & Investigation console.

---

### 14. Exact Implementation Steps
1. Create `frontend/` directory structure (`src/components/`, `src/pages/`, `src/services/`, `src/styles/`).
2. Initialize `package.json` and install dependencies (`react`, `react-dom`, `lucide-react`, `axios`).
3. Define CSS variables and dark-mode glassmorphism tokens in `src/styles/index.css`.
4. Build reusable UI components: `Navbar.jsx`, `StatCard.jsx`, `CameraGrid.jsx`, `AlertFeed.jsx`.
5. Implement `services/api.js` Axios wrapper and `services/websocket.js` WebSocket listener with auto-reconnect.
6. Build pages: `Dashboard.jsx`, `CamerasPage.jsx`, `AlertsPage.jsx`.
7. Wire WebSocket alert notifications into toast popup state container.

---

### 15. Error Handling
- **API Server Offline**: Render top banner warning "Backend connection lost. Retrying...".
- **Empty Stream Grid**: Render empty state card with icon "No active camera feeds found".
- **WebSocket Disconnect**: Implement exponential backoff reconnect (`2s`, `4s`, `8s`) and show yellow pulse indicator.

---

### 16. Testing Requirements
- Unit test component rendering using Jest / React Testing Library (`npm test`).
- Test API error states by mocking HTTP 500 responses.
- Test WebSocket toast popups using mock message dispatchers.

---

### 17. Performance Requirements
- Initial page load time $< 1.5$ seconds.
- Sub-second UI rendering ($< 50$ ms) upon receiving WebSocket alert payloads.
- Smooth 60 FPS video grid playback.

---

### 18. Day 1 Tasks
Initialize React/Vite project setup in `frontend/`, configure dark glassmorphism design tokens in `index.css`, build `Navbar` and `StatCard` components.

---

### 19. Day 2 Tasks
Build `CameraGrid` and `LiveStreamPlayer` components, connect Axios client to backend `/api/v1/cameras` and `/api/v1/dashboard/stats`.

---

### 20. Day 3 Tasks
Implement `AlertFeed` drawer, connect native WebSocket client to `/ws/alerts`, build real-time toast notification popups.

---

### 21. Day 4 Tasks
Add skeleton loaders, empty data states, connection error banners, run production build (`npm run build`), and test integration.

---

### 22. Definition of Done (DoD)
- [ ] React application compiles cleanly without errors (`npm run build`).
- [ ] Dashboard stat cards dynamically render metrics from backend API.
- [ ] Camera grid correctly renders video stream preview cards.
- [ ] WebSocket connection receives backend alert payloads and displays real-time toasts.
- [ ] Code committed to `feature/isha-frontend` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/isha-frontend

# 2. Add implementation files as you build
git add frontend/

# 3. Commit changes
git commit -m "feat(frontend): implement command dashboard and websocket toasts"

# 4. Push to GitHub
git push origin feature/isha-frontend

# 5. Open Pull Request on GitHub:
# feature/isha-frontend  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. Live dashboard displaying 4 stat metric cards populated via REST API.
2. Live camera grid displaying 4 preview streams with online status badges.
3. Live toast notification popping up on screen when a simulated WebSocket alert payload is received.

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Isha, you will create the `frontend/` directory and implementation files as you code. Do NOT commit unnecessary root scaffold files.
