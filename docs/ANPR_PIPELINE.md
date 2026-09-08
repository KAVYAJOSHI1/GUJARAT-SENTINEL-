# ANPR Quality Pipeline (Phase 15B)

The Phase 3 ANPR pipeline (vehicle detection → plate localisation →
CLAHE/threshold/unsharp variants → EasyOCR/PaddleOCR → Indian-plate
normalisation → weighted multi-frame consensus with locking) already
performs well on curated footage. What it did **not** do was explain *why*
a plate came back `UNKNOWN` on real wide-area footage.

Phase 15B adds **explicit quality metrics** and a **failure reason** so the
UI can show:

```
ANPR
UNKNOWN
Reason: LOW_RESOLUTION
Confidence: 0.31
```

instead of a bare `plate = UNKNOWN`.

---

## 1. `PlateQualityAssessor` (`ai/anpr/quality.py`)

Cheap, single-pass OpenCV metrics on the located plate crop:

| Metric | How |
| :--- | :--- |
| `resolution_score` | crop height vs `min_plate_height`, width vs `≈11 px/char × 10 chars` |
| `blur_score` | variance of the Laplacian, mapped `[floor 45 → good 220]` |
| `contrast_score` | grayscale std, mapped `[floor 16 → good 55]` |
| `angle_deg` / `angle_score` | dominant near-horizontal Hough line angle |
| `edge_density` | Canny edge fraction |
| `char_estimate` | ink-run count in the vertical projection profile of the central band |
| `occlusion_score` | edge-density-near-ideal + char-count |
| `overall_score` | `0.28·res + 0.26·blur + 0.18·contrast + 0.12·angle + 0.16·occlusion` |

## 2. Failure reasons (`FailureReason`)

`classify_failure(...)` returns **one** of, in priority order:

| reason | trigger |
| :--- | :--- |
| `NONE` | a valid plate at `confidence ≥ threshold` and `format_score ≥ 0.45` |
| `NO_PLATE` | the locator found no plate-shaped region |
| `LOW_RESOLUTION` | `resolution_score < 0.35` or crop < 55 px wide |
| `OCCLUDED` | near-featureless crop (contrast + occlusion low) or `char_estimate == 0` |
| `BLUR` | `blur_score < 0.28` |
| `OCR_DISAGREEMENT` | ≥ 3 distinct non-UNKNOWN raw reads and no consensus |
| `INVALID_FORMAT` | text was read but does not normalise to a valid Indian plate |
| `LOW_CONFIDENCE` | a candidate plate exists but below the confidence threshold |

Thresholds are **not lowered blindly** — a low-confidence plate is still
reported as `UNKNOWN` with `LOW_CONFIDENCE`, not promoted.

## 3. Perspective correction (`ImagePreprocessor.perspective_correct`)

A 4-point warp: finds the largest convex quadrilateral in the crop (the
plate outline) and, **only if it is clearly non-rectangular**, warps it
front-parallel. Axis-aligned crops (the common case) are returned
untouched — pure recall aid, no regression risk. Feeds the OCR variant set.

## 4. Wire path

```
ai/pipeline.py  process_frame()
   quality_assessor.assess(plate_crop)          -> PlateQuality
   quality_assessor.classify_failure(...)       -> FailureReason
   event["anpr"] = { status, failure_reason, quality, quality_score,
                     plate_quality, ocr_confidence }
        │  POST /events/ai-detection
        ▼
backend  AIDetectionEventIn.resolved_anpr()     (nested block > flat > inferred)
   vehicle_events.anpr_status / anpr_failure_reason / anpr_quality_score /
                  plate_quality        (migration 0013, additive + indexed)
        │
        ▼
GET /vehicles/search  ->  VehicleSighting.anpr_status / anpr_failure_reason /
                          anpr_quality_score
```

Older callers that send no `anpr` block are handled: a readable plate →
`OK`, an `UNKNOWN` plate → `UNKNOWN` + `LOW_CONFIDENCE` (never a bare
null+unknown).

## 5. What is real / requires footage

| | Status |
| :--- | :--- |
| Quality metrics + failure classification | **implemented + tested** (`tests/test_anpr_quality.py`, 14) |
| Perspective correction | **implemented + tested** (safe on axis-aligned + tiny input) |
| Backend storage + surfacing | **implemented + tested** (`backend/tests/test_anpr_fields.py`, 3) |
| Super-resolution model (ESPCN/EDSR) | **not added** — needs opencv-contrib `dnn_superres` + a model file (GPU-friendly). The existing bicubic upscale + unsharp variant is the CPU baseline. |
| Real-footage accuracy numbers | **not claimed** — there is no labelled ground-truth set for the government feeds. `scripts/evaluate_anpr.py` measures against the synthetic set only. |

## 6. Config (pipeline env)

`OCR_ENGINE` (`easyocr` default), `SENTINEL_OCR_CONF_THRESHOLD` (0.50),
`SENTINEL_STABLE_THRESHOLD` (0.75). The quality thresholds live in
`PlateQualityAssessor.__init__` defaults.
