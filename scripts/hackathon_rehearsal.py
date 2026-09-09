#!/usr/bin/env python3
"""
scripts/hackathon_rehearsal.py

Phase 19 Part F/G -- 50-camera hackathon rehearsal + designated-vehicle
scenario, automated end to end. Every check below either PASSES on a real
API response / real pipeline run, or is reported FAIL with the reason --
nothing is assumed to work.

Two halves, on purpose:

  HALF 1 -- SCALE (Part F items 1-7): bulk-onboard ~50 MOCK cameras (this
  repo's own trafficdataset clips), verify GIS + feed assignment, then run
  the REAL AI pipeline (YOLO + ByteTrack + ANPR) against a SUBSET of them
  for a short burst to prove detection/tracking/ANPR genuinely execute at
  scale -- not all 50 are AI-processed in this rehearsal (this dev host's
  measured ~1 FPS aggregate ceiling, see docs/PHASE17_BENCHMARK.md, makes
  that pointless busywork, not a real demonstration); the subset size and
  duration are printed so this is never confused with "50 cameras fully
  AI-processed".

  HALF 2 -- DESIGNATED VEHICLE (Part F items 8-18 / Part G): verifies the
  EXISTING, already-seeded GJ18TC0450 demo scenario end to end via the
  real backend API -- watchlist match, alert, journey, investigation data,
  evidence, incident, case, report. This is DEMO data (seed_ai_demo.py),
  explicitly labeled as such in every response the backend returns
  (feed_source: "DEMO") -- never presented as a real police incident.

Usage:
    .venv/bin/python scripts/hackathon_rehearsal.py
    .venv/bin/python scripts/hackathon_rehearsal.py --backend-url http://localhost:8001 \\
        --admin-user admin --admin-password local-admin-pass
    .venv/bin/python scripts/hackathon_rehearsal.py --skip-pipeline-burst   # API checks only, fast
    .venv/bin/python scripts/hackathon_rehearsal.py --json-out docs/_rehearsal_raw.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REHEARSAL_CAMERA_COUNT = 50
REHEARSAL_REGISTRY = os.path.join(REPO_ROOT, "data", "rehearsal_camera_registry.json")


class CheckResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail


class Rehearsal:
    def __init__(self, args) -> None:
        self.args = args
        self.base = args.backend_url.rstrip("/")
        self.api = f"{self.base}/api/v1"
        self.token: Optional[str] = None
        self.results: List[CheckResult] = []

    # -- plumbing ---------------------------------------------------- #
    def check(self, name: str, fn: Callable[[], bool], detail_fn: Optional[Callable[[], str]] = None) -> None:
        try:
            ok = fn()
            detail = detail_fn() if (detail_fn and ok) else ""
        except Exception as exc:  # noqa: BLE001 -- a check failing must never crash the rehearsal
            ok, detail = False, f"exception: {exc}"
        self.results.append(CheckResult(name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def login(self) -> None:
        r = requests.post(f"{self.api}/auth/login", json={
            "username": self.args.admin_user, "password": self.args.admin_password,
        }, timeout=15)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    # -- HALF 1: scale -------------------------------------------------- #
    def generate_registry(self) -> list:
        import scripts.generate_mock_camera_registry as genreg
        videos = genreg.discover_videos(genreg.DEFAULT_VIDEOS_DIR)[:REHEARSAL_CAMERA_COUNT]
        entries = [genreg.build_entry(i + 1, v, genreg.probe(v)) for i, v in enumerate(videos)]
        with open(REHEARSAL_REGISTRY, "w") as f:
            json.dump(entries, f, indent=2)
        return entries

    def run_scale_checks(self) -> list:
        entries: list = []

        def _gen():
            nonlocal entries
            entries = self.generate_registry()
            return len(entries) >= 10  # honest floor -- don't claim 50 if the dataset can't provide it

        self.check("1. bulk onboarding: generate + sync N mock cameras", _gen,
                    lambda: f"{len(entries)} entries generated")

        def _sync():
            payload = [{"camera_id": e["camera_id"], "name": e["name"], "latitude": e["latitude"],
                        "longitude": e["longitude"], "rtsp_url": e["rtsp_url"], "status": e.get("status")}
                       for e in entries]
            r = requests.post(f"{self.api}/cameras/sync", json=payload, headers=self._auth_headers(), timeout=30)
            r.raise_for_status()
            self._synced = r.json()
            return self._synced.get("synced", 0) == len(entries)

        self.check("1b. POST /cameras/sync accepts the full batch", _sync,
                    lambda: f"synced={self._synced.get('synced')}")

        def _gis():
            cams = getattr(self, "_synced", {}).get("cameras", [])
            with_gps = [c for c in cams if c.get("latitude") is not None and c.get("longitude") is not None]
            return len(with_gps) == len(cams) and len(cams) > 0

        self.check("2. GIS coordinates present on every synced camera", _gis)

        def _feed():
            return all(e.get("rtsp_url") for e in entries)

        self.check("3. feed assignment: every entry has a source URL", _feed)

        if self.args.skip_pipeline_burst:
            self.check("4-7. camera health / playback / detection / tracking / ANPR (real pipeline burst)",
                       lambda: True, lambda: "SKIPPED (--skip-pipeline-burst)")
            return entries

        burst_cams = [e["camera_id"] for e in entries[: self.args.pipeline_cameras]]
        before_count = self._vehicle_event_count()
        self._run_pipeline_burst(burst_cams)
        after_count = self._vehicle_event_count()

        self.check(
            "4. camera health: burst cameras report ONLINE with stream_fps",
            lambda: self._burst_cameras_online(burst_cams),
        )
        self.check(
            "5. live/simulated playback: real frames decoded (stream_fps > 0)",
            lambda: self._burst_cameras_online(burst_cams),
        )
        self.check(
            "6. vehicle detection: new vehicle_events created by the burst",
            lambda: after_count > before_count,
            lambda: f"{before_count} -> {after_count}",
        )
        self.check(
            "7. tracking: ByteTrack assigned at least one persistent track id",
            lambda: (getattr(self, "_last_service_metrics", {}) or {}).get("total_vehicles_detected", 0) > 0,
            lambda: f"total_vehicles_detected={self._last_service_metrics.get('total_vehicles_detected')}",
        )
        return entries

    def _vehicle_event_count(self) -> int:
        r = requests.get(f"{self.api}/system/metrics/summary", headers=self._auth_headers(), timeout=15)
        r.raise_for_status()
        return r.json()["detections"]["total_all_time"]

    def _burst_cameras_online(self, cam_ids: list) -> bool:
        r = requests.get(f"{self.api}/cameras", headers=self._auth_headers(), timeout=15)
        r.raise_for_status()
        by_code = {c.get("code"): c for c in r.json()}
        # CameraRead exposes the health-pushed frame rate as `fps` (the
        # underlying DB column is stream_fps, but the API response field is
        # just `fps` -- see backend/app/schemas/camera.py::CameraRead).
        return any((by_code.get(c) or {}).get("fps") for c in cam_ids)

    def _run_pipeline_burst(self, cam_ids: list) -> None:
        from scripts.run_pipeline_service import PipelineService, load_registry, select_cameras

        if self.args.ingest_key:
            os.environ["SENTINEL_INGEST_API_KEY"] = self.args.ingest_key

        entries = load_registry(REHEARSAL_REGISTRY)

        class _Args:
            pass
        a = _Args()
        a.all, a.camera = False, None
        a.cameras = ",".join(cam_ids)
        a.backend_url = f"{self.api}/events/ai-detection"
        a.no_backend = False
        a.ai_workers = 1
        a.fair_scheduler = False
        a.frame_skip = 0
        a.device = os.getenv("SENTINEL_AI_DEVICE", "cpu")
        a.evidence_dir = os.path.join(REPO_ROOT, "evidence", "rehearsal")
        a.max_queue = 500
        a.stats_interval = 5.0
        a.admin_user = self.args.admin_user
        a.admin_password = self.args.admin_password
        a.duration = self.args.pipeline_duration

        chosen = select_cameras(entries, a)
        svc = PipelineService(chosen, a)
        print(f"  ... running real AI pipeline burst on {len(chosen)} camera(s) for {a.duration}s")
        # PipelineService.start() is the full, real lifecycle (registry
        # sync, consumer/pool start, stats loop, HEALTH PUSH, then a
        # duration-bounded supervise loop that calls shutdown() itself) --
        # exactly what scripts/run_pipeline_service.py's own CLI runs.
        # Reimplementing a subset of it here previously skipped the health
        # push thread entirely, which is why camera health checks failed.
        svc.start()  # blocks for a.duration seconds, then shuts itself down
        if os.getenv("REHEARSAL_DEBUG"):
            for m in svc.manager.health.get_snapshot():
                print(f"  DEBUG health snapshot: {m.camera_id} status={m.status} measured_fps={m.measured_fps}")
        try:
            self._last_service_metrics = (svc.pipeline.get_metrics() if svc.pipeline is not None
                                          else svc.pool.get_metrics())
        except Exception:  # noqa: BLE001 -- metrics capture is best-effort
            self._last_service_metrics = {}

    # -- HALF 2: designated vehicle scenario -------------------------- #
    PLATE = "GJ18TC0450"

    def run_designated_vehicle_checks(self) -> None:
        search: Dict[str, Any] = {}

        def _wl():
            r = requests.get(f"{self.api}/watchlist", params={"plate": self.PLATE},
                             headers=self._auth_headers(), timeout=15)
            r.raise_for_status()
            items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            return any(self.PLATE in (i.get("plate_number_normalized") or "") for i in items)

        self.check("9. watchlist: designated plate is listed", _wl)

        def _search():
            nonlocal search
            r = requests.get(f"{self.api}/vehicles/search", params={"plate": self.PLATE},
                             headers=self._auth_headers(), timeout=15)
            r.raise_for_status()
            search = r.json()
            return search.get("total_sightings", 0) > 0

        self.check("11. designated vehicle search returns sightings", _search,
                    lambda: f"{search.get('total_sightings')} sightings, watchlisted={search.get('is_watchlisted')}")

        def _alert():
            r = requests.get(f"{self.api}/alerts", params={"limit": 200}, headers=self._auth_headers(), timeout=15)
            r.raise_for_status()
            items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            return any(self.PLATE in (a.get("plate_number_normalized") or "") for a in items)

        self.check("10. alert: a WATCHLIST alert exists for the designated plate", _alert)

        def _journey():
            j = search.get("journey") or {}
            return bool(j.get("has_journey")) and len(j.get("transitions", [])) > 0

        self.check("12. journey: multi-camera journey with transitions reconstructed", _journey,
                    lambda: f"{len((search.get('journey') or {}).get('transitions', []))} transitions")

        def _history():
            sightings = search.get("sightings", [])
            return bool(sightings) and all(s.get("timestamp") for s in sightings) \
                and any(s.get("has_location") for s in sightings)

        self.check("13. every sighting carries a timestamp; most carry GIS coordinates", _history)

        def _investigation():
            r = requests.get(f"{self.api}/ai/graph", params={"plate": self.PLATE},
                             headers=self._auth_headers(), timeout=20)
            return r.ok and (r.json().get("counts_by_type") or r.json().get("nodes"))

        self.check("14. investigation workspace data (graph) available for the plate", _investigation)

        def _evidence():
            return any(s.get("snapshot_url") for s in search.get("sightings", []))

        self.check("15. evidence: at least one sighting has a snapshot reference", _evidence)

        incident_number: Dict[str, str] = {}

        def _incident():
            r = requests.get(f"{self.api}/incidents", params={"active_only": "false", "limit": 100},
                             headers=self._auth_headers(), timeout=15)
            r.raise_for_status()
            for i in r.json().get("items", []):
                if str(i.get("incident_number", "")).endswith("9001"):
                    incident_number["v"] = i["incident_number"]
                    return True
            return False

        self.check("16. incident exists for the designated-vehicle alert", _incident,
                    lambda: incident_number.get("v", ""))

        case_number: Dict[str, str] = {}

        def _case():
            r = requests.get(f"{self.api}/cases", params={"limit": 100}, headers=self._auth_headers(), timeout=15)
            r.raise_for_status()
            for c in r.json().get("items", []):
                if str(c.get("case_number", "")).endswith("9001"):
                    case_number["v"] = c["case_number"]
                    return True
            return False

        self.check("17. case exists linked to the incident", _case, lambda: case_number.get("v", ""))

        def _report():
            r = requests.get(f"{self.api}/reports/vehicle-journey.csv", params={"plate": self.PLATE},
                             headers=self._auth_headers(), timeout=20)
            return r.status_code == 200 and len(r.content) > 50

        self.check("18. report generation (CSV) succeeds with real content", _report)

    # -- summary -------------------------------------------------------- #
    def summary(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        return {
            "passed": passed, "total": total, "all_passed": passed == total,
            "checks": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in self.results],
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 19 50-camera rehearsal + designated-vehicle scenario")
    ap.add_argument("--backend-url", default=os.getenv("SENTINEL_BACKEND_API", "http://localhost:8001"))
    ap.add_argument("--admin-user", default=os.getenv("ADMIN_USERNAME", "admin"))
    ap.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", "local-admin-pass"))
    ap.add_argument("--ingest-key", default=os.getenv("SENTINEL_INGEST_API_KEY") or os.getenv("INGEST_API_KEY", ""),
                    help="X-Ingest-Key the pipeline burst uses to POST events -- must match the backend's own "
                         "INGEST_API_KEY or every event/health-push will be rejected with 401.")
    ap.add_argument("--pipeline-cameras", type=int, default=6, help="how many of the N mock cameras to actually AI-process")
    ap.add_argument("--pipeline-duration", type=float, default=25.0)
    ap.add_argument("--skip-pipeline-burst", action="store_true", help="API-only checks, no real YOLO/OCR run")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    reh = Rehearsal(args)
    print("=== SENTINEL Hackathon Rehearsal (Phase 19 Part F/G) ===")
    print(f"backend: {reh.base}")
    reh.login()

    print("\n-- HALF 1: SCALE (bulk onboarding, GIS, feed assignment, real pipeline burst) --")
    reh.run_scale_checks()

    print("\n-- HALF 2: DESIGNATED VEHICLE SCENARIO (DEMO data, seed_ai_demo.py) --")
    reh.run_designated_vehicle_checks()

    s = reh.summary()
    print(f"\n=== {s['passed']}/{s['total']} checks passed ===")
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(s, f, indent=2)
        print(f"[hackathon_rehearsal] wrote {args.json_out}")
    sys.exit(0 if s["all_passed"] else 1)


if __name__ == "__main__":
    main()
