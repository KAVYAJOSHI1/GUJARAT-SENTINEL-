#!/usr/bin/env python3
"""
scripts/anpr_diagnostics.py

Phase 18 Part A/B/D -- ANPR diagnostic/evaluation pipeline.

Runs the REAL detection -> plate-locate -> quality-assess -> preprocess ->
OCR -> normalize -> (optional) temporal-fusion stages against real frames
and reports a rich, explainable per-vehicle diagnostic record -- not just
a bare UNKNOWN. This is a diagnostic tool, not a training/tuning script:
it never adjusts a threshold based on what it sees in one run (see
docs/PHASE18_ANPR_DIAGNOSTICS.md for what, if anything, changed as a
result of running it).

THREE STRATA, NEVER COMBINED (Part D):

  SYNTHETIC        -- rendered plate text dropped into a scene. Out of
                       distribution for the OCR model; characterises
                       pipeline WIRING, not real accuracy.
  MOCK             -- real video frames from trafficdataset/Videos/Videos/
                       (this repo's own dashcam-style traffic footage),
                       fully reproducible, ground truth generally
                       unavailable (no per-frame plate labels exist for
                       this dataset) -> reported UNLABELED / QUALITATIVE.
  REAL_HISTORICAL  -- full-frame JPEGs already present in this repo's
                       evidence/ tree, saved under real Sentinel camera
                       codes (cam01/cam04/cam06/...) during an earlier
                       session's RTSP smoke test (see
                       docs/GOVERNMENT_FEED_READINESS.md Sec 8: "Earlier
                       real cam04/cam06 smoke (Phase 11): RTSP auth OK,
                       YOLO+ByteTrack run, events delivered, plates
                       UNKNOWN"). The real government RTSP/HLS endpoints
                       are NOT reachable from this development
                       environment today (verified: both time out) --
                       these archived frames are the best available real-
                       camera material and are re-analyzed here with the
                       CURRENT pipeline. Their exact capture provenance
                       (a genuinely live feed vs. a substituted test
                       source at capture time) cannot be independently
                       re-verified from the file alone, so this stratum
                       is labeled REAL_HISTORICAL / PROVENANCE-UNCERTAIN,
                       distinct from a certified live-feed result, and
                       -- because no ground-truth plate list exists for
                       these frames -- also UNLABELED / QUALITATIVE.

No stratum's numbers are ever averaged together. A stratum without ground
truth reports detection/failure-reason statistics only -- never a
fabricated "accuracy".

Usage:
    .venv/bin/python scripts/anpr_diagnostics.py --stratum synthetic
    .venv/bin/python scripts/anpr_diagnostics.py --stratum mock --limit 40
    .venv/bin/python scripts/anpr_diagnostics.py --stratum real_historical --limit 60
    .venv/bin/python scripts/anpr_diagnostics.py --stratum all --json-out docs/_phase18_anpr_raw.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ai.anpr.plate_locator import PlateLocator  # noqa: E402
from ai.anpr.plate_track_state import PlateTrackStore  # noqa: E402
from ai.anpr.preprocess import ImagePreprocessor  # noqa: E402
from ai.anpr.quality import FailureReason, PlateQualityAssessor  # noqa: E402
from ai.detection.vehicle_detector import VehicleDetector  # noqa: E402
from ai.ocr.normalizer import PlateNormalizer  # noqa: E402
from ai.ocr.ocr_engine import OCREngine  # noqa: E402
from ai.tracking.tracker import ByteTrackTracker  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOCK_VIDEO_GLOB = os.path.join(REPO_ROOT, "trafficdataset", "Videos", "Videos", "*.MOV")
REAL_EVIDENCE_DIRS = [
    os.path.join(REPO_ROOT, "evidence"),
    os.path.join(REPO_ROOT, "evidence", "live"),
    os.path.join(REPO_ROOT, "evidence", "live_sentinel"),
]
REAL_CAMERA_CODE_PREFIXES = ("cam01", "cam02", "cam03", "cam04", "cam05", "cam06", "cam07", "cam08")


@dataclass
class DiagnosticRecord:
    stratum: str
    source_file: str
    frame_index: Optional[int] = None
    track_id: Optional[int] = None
    vehicle_detected: bool = False
    vehicle_confidence: Optional[float] = None
    plate_located: bool = False
    plate_locator_confidence: Optional[float] = None
    plate_crop_width: int = 0
    plate_crop_height: int = 0
    plate_aspect_ratio: Optional[float] = None
    blur_score: Optional[float] = None
    contrast_score: Optional[float] = None
    angle_deg: Optional[float] = None
    edge_density: Optional[float] = None
    char_estimate: Optional[int] = None
    overall_quality_score: Optional[float] = None
    ocr_raw_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    normalized_plate: Optional[str] = None
    format_score: Optional[float] = None
    final_confidence: Optional[float] = None
    failure_reason: str = FailureReason.NO_PLATE
    temporal_plate: Optional[str] = None
    temporal_confidence: Optional[float] = None
    temporal_stable: Optional[bool] = None
    temporal_method: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AnprDiagnosticEngine:
    """Reuses the exact real pipeline components -- no shortcuts, no
    reimplemented OCR logic -- just instrumented to report every
    intermediate value instead of collapsing straight to UNKNOWN."""

    def __init__(self, device: str = "cpu") -> None:
        self.detector = VehicleDetector(device=device)
        self.locator = PlateLocator()
        self.preprocessor = ImagePreprocessor()
        self.quality = PlateQualityAssessor()
        self.ocr = OCREngine()
        self.normalizer = PlateNormalizer()
        self.track_store = PlateTrackStore()

    def diagnose_frame(
        self, frame: np.ndarray, *, stratum: str, source_file: str,
        frame_index: Optional[int] = None, tracker: Optional[ByteTrackTracker] = None,
        camera_id: str = "diag",
    ) -> List[DiagnosticRecord]:
        records: List[DiagnosticRecord] = []
        try:
            detections = self.detector.detect(frame)
        except Exception:  # noqa: BLE001
            detections = []

        if not detections:
            records.append(DiagnosticRecord(
                stratum=stratum, source_file=source_file, frame_index=frame_index,
                vehicle_detected=False, failure_reason=FailureReason.NO_PLATE,
            ))
            return records

        if tracker is not None:
            online = tracker.update(detections)
            tracked = [{"class": t.get("class") or "vehicle", "confidence": float(t.get("score", 0.0)),
                        "bbox": [int(round(v)) for v in t["bbox"]], "track_id": t["track_id"]} for t in online]
        else:
            tracked = [{"class": d["class"], "confidence": d["confidence"], "bbox": d["bbox"], "track_id": None}
                       for d in detections]

        for veh in tracked:
            try:
                crop = self.detector.crop_vehicle(frame, veh["bbox"])
            except Exception:  # noqa: BLE001
                crop = None
            rec = self._diagnose_vehicle_crop(
                crop, stratum=stratum, source_file=source_file, frame_index=frame_index,
                track_id=veh["track_id"], camera_id=camera_id,
            )
            rec.vehicle_detected = True
            rec.vehicle_confidence = round(float(veh["confidence"]), 4)
            records.append(rec)
        return records

    def _diagnose_vehicle_crop(
        self, crop: Optional[np.ndarray], *, stratum: str, source_file: str,
        frame_index: Optional[int], track_id: Optional[int], camera_id: str,
    ) -> DiagnosticRecord:
        rec = DiagnosticRecord(stratum=stratum, source_file=source_file, frame_index=frame_index, track_id=track_id)
        if crop is None or crop.size == 0:
            rec.failure_reason = FailureReason.NO_PLATE
            return rec

        loc = self.locator.locate_plate(crop)
        plate_crop = loc["plate_crop"]
        located = bool(loc.get("confidence", 0.0) > 0.0)
        rec.plate_located = located
        rec.plate_locator_confidence = round(float(loc.get("confidence", 0.0)), 4)

        q = self.quality.assess(plate_crop)
        rec.plate_crop_width = q.width
        rec.plate_crop_height = q.height
        rec.plate_aspect_ratio = round(q.width / q.height, 3) if q.height else None
        rec.blur_score = q.blur_score
        rec.contrast_score = q.contrast_score
        rec.angle_deg = q.angle_deg
        rec.edge_density = q.edge_density
        rec.char_estimate = q.char_estimate
        rec.overall_quality_score = q.overall_score

        variants = self.preprocessor.variants(plate_crop) if located else []
        if variants:
            ocr_res = self.ocr.extract_best(variants, self.normalizer)
        else:
            ocr_res = {"raw_text": "UNKNOWN", "confidence": 0.0}
        rec.ocr_raw_text = ocr_res["raw_text"]
        rec.ocr_confidence = round(float(ocr_res["confidence"]), 4)

        normalized = self.normalizer.normalize(rec.ocr_raw_text)
        rec.normalized_plate = normalized
        rec.format_score = round(float(self.normalizer.format_score(normalized)), 4)
        rec.final_confidence = rec.ocr_confidence

        if track_id is not None:
            st = self.track_store.observe(
                camera_id, track_id, normalized, rec.ocr_confidence,
                plate_quality=q.overall_score, format_score=rec.format_score,
            )
            res = st.resolve()
            rec.temporal_plate = res["plate"]
            rec.temporal_confidence = res["confidence"]
            rec.temporal_stable = res["stable"]
            rec.temporal_method = res["method"]
            if res["stable"]:
                rec.final_confidence = res["confidence"]

        rec.failure_reason = self.quality.classify_failure(
            q, located=located, ocr_text=rec.ocr_raw_text, normalized_plate=normalized,
            format_score=rec.format_score, confidence=rec.final_confidence,
            raw_reads=[rec.ocr_raw_text],
        )
        return rec

    def diagnose_synthetic_plate(self, plate_crop: np.ndarray, *, source_file: str) -> DiagnosticRecord:
        """SYNTHETIC stratum bypasses YOLO vehicle detection entirely (a
        rendered plate on a plain background is not a recognisable vehicle
        shape -- the point of this stratum is to characterise the plate-
        locate -> OCR -> normalize sub-pipeline in isolation, matching
        scripts/evaluate_anpr.py's existing convention)."""
        rec = self._diagnose_vehicle_crop(
            plate_crop, stratum="SYNTHETIC", source_file=source_file, frame_index=None,
            track_id=None, camera_id="synthetic",
        )
        rec.vehicle_detected = True
        rec.vehicle_confidence = 1.0
        return rec


# ===================================================================== #
# frame sources
# ===================================================================== #
def _render_plate(text: str, w: int = 560, h: int = 150) -> np.ndarray:
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (0, 0, 0), 4)
    f = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, f, 2.6, 6)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), f, 2.6, (0, 0, 0), 6, cv2.LINE_AA)
    return img


def synthetic_vehicle_crops(n: int) -> List[tuple]:
    """(vehicle_crop, plate_text) pairs -- a rendered plate embedded in a
    plain "vehicle body" region, matching what VehicleDetector.crop_vehicle()
    would hand the plate locator downstream. Never claims to exercise YOLO
    itself (see AnprDiagnosticEngine.diagnose_synthetic_plate's docstring)."""
    states = ["GJ", "MH", "DL", "KA", "RJ", "TN", "UP", "HR"]
    rng = np.random.default_rng(7)
    out = []
    for i in range(n):
        s = states[i % len(states)]
        d = f"{rng.integers(1, 40):02d}"
        letters = "".join(chr(65 + int(x)) for x in rng.integers(0, 26, size=int(rng.integers(1, 4))))
        num = f"{rng.integers(1, 10000):04d}"
        plate = f"{s}{d}{letters}{num}"
        img = _render_plate(plate)
        vehicle_crop = np.full((260, 420, 3), 70, np.uint8)
        vehicle_crop[:] = rng.integers(50, 110, size=3)
        ph, pw = 90, 260
        pr = cv2.resize(img, (pw, ph))
        y, x = 140, 80
        vehicle_crop[y:y + ph, x:x + pw] = pr
        out.append((vehicle_crop, plate))
    return out


def mock_video_frames(limit: int, videos: int = 6, stride: int = 15):
    files = sorted(glob.glob(MOCK_VIDEO_GLOB))[:videos]
    n = 0
    for f in files:
        cap = cv2.VideoCapture(f)
        idx = 0
        while cap.isOpened() and n < limit:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                yield f, idx, frame
                n += 1
            idx += 1
        cap.release()
        if n >= limit:
            break


def real_historical_frames(limit: int):
    seen = set()
    n = 0
    for d in REAL_EVIDENCE_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png")) or fn.endswith("_crop.jpg"):
                continue
            if not fn.startswith(REAL_CAMERA_CODE_PREFIXES):
                continue
            path = os.path.join(d, fn)
            key = os.path.getsize(path) if os.path.exists(path) else None
            dedup_key = (fn, key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            img = cv2.imread(path)
            if img is None:
                continue
            yield path, None, img
            n += 1
            if n >= limit:
                return


# ===================================================================== #
# reporting
# ===================================================================== #
def summarize(stratum: str, records: List[DiagnosticRecord], *, ground_truth: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    total = len(records)
    vehicle_detected = sum(1 for r in records if r.vehicle_detected)
    plate_located = sum(1 for r in records if r.plate_located)
    non_unknown = sum(1 for r in records if r.normalized_plate and r.normalized_plate != "UNKNOWN")
    unknown = total - non_unknown
    failure_hist = Counter(r.failure_reason for r in records if r.normalized_plate in (None, "UNKNOWN"))

    summary: Dict[str, Any] = {
        "stratum": stratum,
        "total_samples": total,
        "vehicle_detected": vehicle_detected,
        "vehicle_detected_rate": round(vehicle_detected / total, 3) if total else None,
        "plate_located": plate_located,
        "plate_located_rate": round(plate_located / vehicle_detected, 3) if vehicle_detected else None,
        "plate_read_non_unknown": non_unknown,
        "unknown_count": unknown,
        "unknown_rate": round(unknown / total, 3) if total else None,
        "failure_reason_breakdown": dict(failure_hist),
    }

    if ground_truth:
        exact = char_acc_list = 0
        char_accs = []
        labeled = 0
        for r in records:
            truth = ground_truth.get(r.source_file)
            if truth is None:
                continue
            labeled += 1
            pred = r.normalized_plate or "UNKNOWN"
            if pred == truth:
                exact += 1
            n = max(len(pred), len(truth)) or 1
            same = sum(1 for i in range(min(len(pred), len(truth))) if pred[i] == truth[i])
            char_accs.append(same / n)
        summary["ground_truth_methodology"] = "filename/manifest-provided exact plate labels"
        summary["labeled_samples"] = labeled
        summary["exact_plate_accuracy"] = round(exact / labeled, 3) if labeled else None
        summary["character_accuracy"] = round(sum(char_accs) / len(char_accs), 3) if char_accs else None
    else:
        summary["ground_truth_methodology"] = "UNLABELED / QUALITATIVE -- no ground truth available for this stratum"
        summary["exact_plate_accuracy"] = None
        summary["character_accuracy"] = None

    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 18 ANPR diagnostic/evaluation pipeline")
    ap.add_argument("--stratum", choices=["synthetic", "mock", "real_historical", "all"], default="synthetic")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    engine = AnprDiagnosticEngine()
    all_records: List[DiagnosticRecord] = []
    summaries: List[Dict[str, Any]] = []

    strata = ["synthetic", "mock", "real_historical"] if args.stratum == "all" else [args.stratum]

    for stratum in strata:
        records: List[DiagnosticRecord] = []
        ground_truth: Optional[Dict[str, str]] = None
        if stratum == "synthetic":
            ground_truth = {}
            for i, (crop, plate) in enumerate(synthetic_vehicle_crops(args.limit)):
                source_file = f"synthetic-{i}"
                ground_truth[source_file] = plate
                records.append(engine.diagnose_synthetic_plate(crop, source_file=source_file))
        elif stratum == "mock":
            tracker = ByteTrackTracker(track_thresh=0.25, new_track_thresh=0.5, match_thresh=0.85, track_buffer=30, frame_rate=30)
            for f, idx, frame in mock_video_frames(args.limit):
                records.extend(engine.diagnose_frame(frame, stratum="MOCK", source_file=f, frame_index=idx, tracker=tracker, camera_id=f))
        else:
            for path, idx, frame in real_historical_frames(args.limit):
                records.extend(engine.diagnose_frame(frame, stratum="REAL_HISTORICAL", source_file=path, frame_index=idx))

        all_records.extend(records)
        s = summarize(stratum.upper(), records, ground_truth=ground_truth)
        summaries.append(s)
        print("\n" + "=" * 78)
        print(f" ANPR DIAGNOSTICS -- {s['stratum']}"
              + ("" if stratum != "real_historical" else "  (PROVENANCE-UNCERTAIN, see module docstring)"))
        print("=" * 78)
        for k, v in s.items():
            if k in ("stratum",):
                continue
            print(f"  {k:28s} {v}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({
                "summaries": summaries,
                "records": [r.to_dict() for r in all_records],
            }, f, indent=2, default=str)
        print(f"\n[anpr_diagnostics] wrote {args.json_out}")


if __name__ == "__main__":
    main()
