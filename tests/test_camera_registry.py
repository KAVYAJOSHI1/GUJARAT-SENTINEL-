import json
import os
import unittest

REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "camera_registry.json"
)

EXPECTED_SENTINEL_CATALOGUE = [
    {"id": "cam01", "name": "01 Chiman bhai Bridge"},
    {"id": "cam02", "name": "02 Janpath"},
    {"id": "cam03", "name": "03 O.N.G.C. Office"},
    {"id": "cam04", "name": "04 Paldi Circle"},
    {"id": "cam05", "name": "05 Visat teen Rasta"},
    {"id": "cam06", "name": "06 Timbavadi gate-Junagadh"},
    {"id": "cam07", "name": "07 hero-showroom-gir-somnath"},
    {"id": "cam08", "name": "08 majewadi-gate-junagadh"},
    {"id": "cam09", "name": "09 new-bypass-near-by-circle-junagadh-2"},
    {"id": "cam10", "name": "10 char-chowk-road-2-junagadh"},
    {"id": "cam11", "name": "11 dolatpara-junagadh"},
    {"id": "cam12", "name": "12 Tri Mandir Adalaj Tollnaka"},
    {"id": "cam13", "name": "13 CN Vidhyalaya"},
    {"id": "cam14", "name": "14 Delight RLVD"},
    {"id": "cam15", "name": "15 Suvidha park"},
    {"id": "cam16", "name": "16 Visat P2"},
    {"id": "cam17", "name": "17 Rajkot Bus Port CCTV"},
    {"id": "cam18", "name": "18 Rajkot CCTV"},
    {"id": "cam19", "name": "19 KHAPARIA GRAM PANCHAYAT , TALUKA GANDEVI, DISTRICT NAVSARI"},
    {"id": "cam20", "name": "20 Mohanpura"},
    {"id": "cam21", "name": "23 Patan Dethali Char Rasta"},
    {"id": "cam22", "name": "28 BK Mervada tran Rasta"},
    {"id": "cam23", "name": "30 kheram"},
    {"id": "cam24", "name": "33 dehgam"},
    {"id": "cam25", "name": "34 dhanori"},
    {"id": "cam26", "name": "35 TANKAL"},
    {"id": "cam27", "name": "36 bilimora"},
    {"id": "cam28", "name": "37 bilimora"},
    {"id": "cam29", "name": "38 bilimora"},
    {"id": "cam30", "name": "Gandhidham Rambaugh p2"}
]


class TestCameraRegistryGIS(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(os.path.exists(REGISTRY_PATH), f"Registry file missing: {REGISTRY_PATH}")
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            cls.registry = json.load(f)

    def test_total_camera_count(self):
        """Verify registry contains exactly 30 cameras."""
        self.assertEqual(len(self.registry), 30, f"Expected 30 cameras, found {len(self.registry)}")

    def test_original_names_preserved(self):
        """Verify every camera retains its original Sentinel ID and Name without modification."""
        reg_map = {c["camera_id"]: c["name"] for c in self.registry}
        for item in EXPECTED_SENTINEL_CATALOGUE:
            cid = item["id"]
            expected_name = item["name"]
            self.assertIn(cid, reg_map, f"Missing camera ID in registry: {cid}")
            self.assertEqual(
                reg_map[cid],
                expected_name,
                f"Name mismatch for {cid}: expected '{expected_name}', got '{reg_map[cid]}'"
            )

    def test_coordinate_pair_integrity(self):
        """Verify latitude and longitude are either both present (floats) or both null."""
        for cam in self.registry:
            lat = cam.get("latitude")
            lon = cam.get("longitude")
            if lat is None or lon is None:
                self.assertIsNone(lat, f"Latitude present without longitude in {cam['camera_id']}")
                self.assertIsNone(lon, f"Longitude present without latitude in {cam['camera_id']}")
            else:
                self.assertIsInstance(lat, (int, float), f"Latitude must be a float in {cam['camera_id']}")
                self.assertIsInstance(lon, (int, float), f"Longitude must be a float in {cam['camera_id']}")

    def test_coordinate_range(self):
        """Verify latitude is within [-90, 90] and longitude is within [-180, 180]."""
        for cam in self.registry:
            lat = cam.get("latitude")
            lon = cam.get("longitude")
            if lat is not None and lon is not None:
                self.assertGreaterEqual(lat, -90.0, f"Latitude below -90 in {cam['camera_id']}")
                self.assertLessEqual(lat, 90.0, f"Latitude above 90 in {cam['camera_id']}")
                self.assertGreaterEqual(lon, -180.0, f"Longitude below -180 in {cam['camera_id']}")
                self.assertLessEqual(lon, 180.0, f"Longitude above 180 in {cam['camera_id']}")
                # Extra sanity check: Gujarat coordinates should be roughly lat [20, 25], lon [68, 74]
                self.assertGreaterEqual(lat, 20.0, f"Latitude outside Gujarat bounds in {cam['camera_id']}")
                self.assertLessEqual(lat, 25.0, f"Latitude outside Gujarat bounds in {cam['camera_id']}")
                self.assertGreaterEqual(lon, 68.0, f"Longitude outside Gujarat bounds in {cam['camera_id']}")
                self.assertLessEqual(lon, 74.0, f"Longitude outside Gujarat bounds in {cam['camera_id']}")

    def test_unresolved_cameras_not_faked(self):
        """Verify that UNRESOLVED cameras are assigned null coordinates instead of fake values."""
        for cam in self.registry:
            confidence = cam.get("location_confidence")
            if confidence == "UNRESOLVED":
                self.assertIsNone(cam.get("latitude"), f"UNRESOLVED camera {cam['camera_id']} has non-null latitude")
                self.assertIsNone(cam.get("longitude"), f"UNRESOLVED camera {cam['camera_id']} has non-null longitude")
                self.assertFalse(cam.get("location_verified"), f"UNRESOLVED camera {cam['camera_id']} set verified=true")

    def test_location_source_distinction(self):
        """Verify location_source clearly distinguishes application enrichment from Sentinel metadata."""
        for cam in self.registry:
            source = cam.get("location_source")
            self.assertEqual(
                source,
                "application_geocoding",
                f"Invalid location_source in {cam['camera_id']}: expected 'application_geocoding', got '{source}'"
            )
            # Guarantee no claim of 'Sentinel-provided' coordinates
            self.assertNotIn("sentinel", str(source).lower())

    def test_required_schema_keys(self):
        """Verify every record contains all 18 required schema fields."""
        required_keys = {
            "camera_id", "name", "latitude", "longitude", "resolved_address",
            "city", "district", "state", "location_source", "location_confidence",
            "location_verified", "department", "status", "codec", "resolution",
            "rtsp_url", "hls_url", "whep_url"
        }
        for cam in self.registry:
            missing = required_keys - set(cam.keys())
            self.assertEqual(len(missing), 0, f"Camera {cam.get('camera_id')} missing keys: {missing}")

    def test_department_unknown_default(self):
        """Verify department is 'UNKNOWN' unless independently verified."""
        for cam in self.registry:
            self.assertEqual(
                cam.get("department"),
                "UNKNOWN",
                f"Department in {cam['camera_id']} should be 'UNKNOWN', got '{cam.get('department')}'"
            )


if __name__ == "__main__":
    unittest.main()
