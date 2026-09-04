// ─── Offline fallback data for the GIS / Investigation console ────────────────
// Vishakha · feature/vishakha-investigation.
//
// Mirrors the shapes the backend serves so real payloads and this mock are
// interchangeable (see services/investigationApi.js for the normalisers):
//   - CAMERA_GEOJSON        → GET /api/v1/cameras/geojson
//   - MOCK_VEHICLE_SEARCH   → GET /api/v1/vehicles/search?plate=GJ01AB1234
//
// Camera coordinates are the application-geocoded Gujarat CCTV grid documented
// in docs/gis_metadata.md on the `testing` branch (30 cameras). This file does
// NOT touch Isha's lib/mockData.js.

const CAMERA_ROWS = [
  ["cam01", "Chiman Bhai Bridge", 23.069362, 72.587224, "Ahmedabad", "active"],
  ["cam02", "Janpath", 23.029815, 72.571432, "Ahmedabad", "active"],
  ["cam03", "O.N.G.C. Office", 23.1118, 72.5855, "Ahmedabad", "active"],
  ["cam04", "Paldi Circle", 23.01258, 72.56412, "Ahmedabad", "alert"],
  ["cam05", "Visat Teen Rasta", 23.1157, 72.5815, "Ahmedabad", "active"],
  ["cam06", "Timbavadi Gate", 21.503307, 70.4335, "Junagadh", "active"],
  ["cam07", "Hero Showroom, Veraval", 20.91011, 70.365279, "Gir Somnath", "offline"],
  ["cam08", "Majewadi Gate", 21.535478, 70.460007, "Junagadh", "active"],
  ["cam09", "New Bypass Circle 2", 21.586345, 70.447325, "Junagadh", "active"],
  ["cam10", "Char Chowk Road 2", 21.52245, 70.45781, "Junagadh", "active"],
  ["cam11", "Dolatpara", 21.558757, 70.465922, "Junagadh", "active"],
  ["cam12", "Tri Mandir Adalaj Tollnaka", 23.178482, 72.572128, "Gandhinagar", "active"],
  ["cam13", "CN Vidhyalaya", 23.018995, 72.548889, "Ahmedabad", "active"],
  ["cam14", "Delight RLVD", 23.02451, 72.55623, "Ahmedabad", "alert"],
  ["cam15", "Suvidha Park", 23.00342, 72.55981, "Ahmedabad", "active"],
  ["cam16", "Visat P2", 23.1162, 72.582, "Ahmedabad", "active"],
  ["cam17", "Rajkot Bus Port", 22.29215, 70.79948, "Rajkot", "active"],
  ["cam18", "Rajkot Trikon Baug", 22.305326, 70.802838, "Rajkot", "offline"],
  ["cam19", "Khaparia Gram Panchayat", 20.863404, 73.048965, "Navsari", "active"],
  ["cam20", "Mohanpura Square", 23.59821, 72.96452, "Sabarkantha", "active"],
  ["cam21", "Patan Dethali Char Rasta", 23.916615, 72.361147, "Patan", "active"],
  ["cam22", "BK Mervada Tran Rasta", 24.23841, 72.1852, "Banaskantha", "active"],
  ["cam23", "Khergam Tran Rasta", 20.65582, 73.08745, "Navsari", "offline"],
  ["cam24", "Dehgam", 23.164033, 72.881832, "Gandhinagar", "active"],
  ["cam25", "Dhanori", 20.838862, 73.023955, "Navsari", "active"],
  ["cam26", "Tankal", 20.860591, 73.130617, "Navsari", "active"],
  ["cam27", "Bilimora North", 20.767169, 72.969345, "Navsari", "active"],
  ["cam28", "Bilimora East", 20.766008, 73.007151, "Navsari", "active"],
  ["cam29", "Bilimora Somnath Road", 20.75841, 72.95682, "Navsari", "alert"],
  ["cam30", "Gandhidham Rambaugh P2", 23.07682, 70.13215, "Kutch", "active"],
];

export const CAMERA_GEOJSON = {
  type: "FeatureCollection",
  features: CAMERA_ROWS.map(([id, name, lat, lng, district, status]) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: { camera_id: id, name, district, status },
  })),
};

// Plain-array view of the same cameras (used when a GeoJSON layer is not needed).
export const GIS_CAMERAS = CAMERA_ROWS.map(([id, name, lat, lng, district, status]) => ({
  id,
  name,
  district,
  lat,
  lng,
  status,
}));

// Sample vehicle history for the demo plate. Deliberately stored OUT OF
// timestamp order so the timeline / polyline sorting is exercised
// (DEVELOPER_README §16 — "out-of-order timestamps").
export const MOCK_VEHICLE_SEARCH = {
  status: "success",
  query_plate: "GJ01AB1234",
  total_sightings: 5,
  summary: {
    first_seen: "2026-09-01T09:12:00Z",
    last_seen: "2026-09-01T10:41:30Z",
    total_cameras: 5,
    has_active_watchlist_hit: true,
  },
  sightings: [
    {
      event_id: "EVT_2026090103",
      camera_id: "cam13",
      camera_name: "CN Vidhyalaya",
      timestamp: "2026-09-01T10:05:12Z",
      location: { latitude: 23.018995, longitude: 72.548889 },
      evidence_snapshot_url: "",
      ocr_confidence: 0.947,
      vehicle_type: "car",
    },
    {
      event_id: "EVT_2026090101",
      camera_id: "cam02",
      camera_name: "Janpath",
      timestamp: "2026-09-01T09:12:00Z",
      location: { latitude: 23.029815, longitude: 72.571432 },
      evidence_snapshot_url: "",
      ocr_confidence: 0.912,
      vehicle_type: "car",
    },
    {
      event_id: "EVT_2026090105",
      camera_id: "cam15",
      camera_name: "Suvidha Park",
      timestamp: "2026-09-01T10:41:30Z",
      location: { latitude: 23.00342, longitude: 72.55981 },
      evidence_snapshot_url: "",
      ocr_confidence: 0.889,
      vehicle_type: "car",
    },
    {
      event_id: "EVT_2026090102",
      camera_id: "cam14",
      camera_name: "Delight RLVD",
      timestamp: "2026-09-01T09:47:41Z",
      location: { latitude: 23.02451, longitude: 72.55623 },
      evidence_snapshot_url: "",
      ocr_confidence: 0.931,
      vehicle_type: "car",
    },
    {
      event_id: "EVT_2026090104",
      camera_id: "cam04",
      camera_name: "Paldi Circle",
      timestamp: "2026-09-01T10:23:58Z",
      location: { latitude: 23.01258, longitude: 72.56412 },
      evidence_snapshot_url: "",
      ocr_confidence: 0.958,
      vehicle_type: "car",
    },
  ],
};

// Gujarat state centroid — initial map view (DEVELOPER_README §14.3).
export const GUJARAT_CENTER = [23.0225, 72.5714];
export const GUJARAT_ZOOM = 7;
export const CITY_ZOOM = 12;
// Close-up used when the console is opened on one specific camera
// (CameraModal hand-off: /investigation?cam=<id>).
export const FOCUS_ZOOM = 15;
