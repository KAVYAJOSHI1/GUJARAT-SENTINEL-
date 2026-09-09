# Phase 18 — ANPR Diagnostics: Why Real Footage Returns UNKNOWN

> **How to read this document:** every number below was produced by
> `scripts/anpr_diagnostics.py` against real files in this repository on
> 2026-09-09. Reproduce any table with the command printed above it. The
> three strata (SYNTHETIC / MOCK / REAL_HISTORICAL) are **never** combined
> into one accuracy figure — see §4 for exactly why not.

---

## 1. The question this document answers

Earlier real-camera smoke testing (Phase 11, `GOVERNMENT_FEED_READINESS.md`
§8) found that plates read `UNKNOWN` on real Sentinel footage. That was
true, but not *explained* — a bare `UNKNOWN` doesn't say whether the
camera saw a bumper, saw nothing, or saw a perfectly good plate that OCR
just missed. This phase built a diagnostic pipeline
(`scripts/anpr_diagnostics.py`) that runs the real detection → plate-
locate → quality-assess → OCR → normalize → temporal-fusion stages and
reports **every intermediate value**, then ran it against the best real
material actually available in this environment.

## 2. Honesty about what "REAL" means here

The real government RTSP/HLS endpoints (`103.250.160.189:8554`,
`cctv.corp8.cloud`) are **confirmed unreachable from this development
environment** — both a raw TCP connect to the RTSP port and an HTTPS
request to the HLS host timed out completely during this phase. No fresh
real-camera frame could be captured in this session.

What *is* real: `evidence/`, `evidence/live/`, and `evidence/live_sentinel/`
already contain 282 full-frame JPEGs saved under genuine Sentinel camera
codes (`cam01`, `cam04`, `cam06`, …) from an earlier session's RTSP smoke
test (`GOVERNMENT_FEED_READINESS.md` §8: "Earlier real cam04/cam06 smoke
(Phase 11): RTSP auth OK, YOLO+ByteTrack run, events delivered, plates
UNKNOWN"). This phase re-analyzed 136 of those frames with the **current**
pipeline. Their exact capture provenance (a genuinely live feed at that
moment, vs. a test source substituted into that camera's registry slot)
cannot be independently re-verified from the file alone — so this stratum
is labeled **REAL_HISTORICAL / PROVENANCE-UNCERTAIN**, distinct from a
certified live-feed result, and never presented as "measured real-feed
accuracy" (there is no ground-truth plate list for these frames either).

## 3. Results, one stratum at a time

### SYNTHETIC (n=30) — rendered plate text, out-of-distribution for the OCR model

```
.venv/bin/python scripts/anpr_diagnostics.py --stratum synthetic --limit 30
```

| Metric | Value |
| :-- | --: |
| Vehicle-crop provided | 30/30 (100%) — bypasses YOLO by design, see script docstring |
| Plate located | 30/30 (100%) |
| UNKNOWN rate | 0% |
| Exact plate accuracy | 70.0% |
| Character accuracy | 96.1% |

Characterizes the plate-locate → OCR → normalize **wiring**, not real-
world accuracy — rendered fonts on a plain background are easier than any
real plate.

### MOCK (n=62 detected vehicles) — real video frames, this repo's own trafficdataset clips

```
.venv/bin/python scripts/anpr_diagnostics.py --stratum mock --limit 40
```

| Metric | Value |
| :-- | --: |
| Vehicle detected | 62/62 (100% of sampled frames with a vehicle) |
| Plate located | 62/62 (100%) |
| **UNKNOWN rate** | **87.1%** (54/62) |
| Ground truth | **UNLABELED / QUALITATIVE** — no per-frame plate labels exist for this dataset |

Failure-reason breakdown (of the 54 UNKNOWN):

| Reason | Count | Share |
| :-- | --: | --: |
| OCCLUDED | 32 | 59% |
| BLUR | 15 | 28% |
| LOW_RESOLUTION | 6 | 11% |
| LOW_CONFIDENCE | 1 | 2% |

### REAL_HISTORICAL (n=136 detected vehicles) — archived real-camera-code JPEGs

```
.venv/bin/python scripts/anpr_diagnostics.py --stratum real_historical --limit 60
```

| Metric | Value |
| :-- | --: |
| Vehicle detected | 135/136 (99.3%) |
| Plate located | 135/135 (100%) |
| **UNKNOWN rate** | **97.1%** (132/135) |
| Ground truth | **UNLABELED / QUALITATIVE** — no ground-truth plate list exists for these frames |

Failure-reason breakdown (of the 132 UNKNOWN):

| Reason | Count | Share |
| :-- | --: | --: |
| OCCLUDED | 105 | 80% |
| LOW_RESOLUTION | 16 | 12% |
| LOW_CONFIDENCE | 9 | 7% |
| NO_PLATE | 1 | 1% |
| BLUR | 1 | 1% |

**This is the explainable version of "real footage returns UNKNOWN":**
the dominant, measured cause on both real strata is `OCCLUDED` — which in
this codebase's classifier fires primarily on near-zero `char_estimate`
(the plate-locator region contains too few character-shaped ink blobs to
be a readable plate), not literal dirt/object occlusion. Root cause
investigated directly (§5 below), not assumed.

## 4. Why SYNTHETIC/MOCK/REAL_HISTORICAL are never combined

A single "ANPR accuracy: X%" number averaging these three would be
actively misleading — SYNTHETIC's 70% exact accuracy describes rendered
text on a blank background, not a real plate at any distance; MOCK and
REAL_HISTORICAL have **no ground truth at all**, so any "accuracy"
computed for them would be fabricated, not measured. `scripts/
anpr_diagnostics.py` structurally cannot compute `exact_plate_accuracy`
for a stratum with no ground-truth mapping — it reports `null` and labels
the methodology `UNLABELED / QUALITATIVE`, per the task brief's explicit
instruction. This mirrors the existing convention in
`scripts/evaluate_anpr.py`'s synthetic-vs-real labeling.

## 5. Root-cause check on the dominant OCCLUDED failure (not blind tuning)

Before considering any change to the failure-reason taxonomy or quality
thresholds, the actual metric distributions among OCCLUDED-classified
REAL_HISTORICAL samples were inspected directly:

| Metric (n=108 OCCLUDED samples) | Median | Notes |
| :-- | --: | :-- |
| `char_estimate` | 0 | the dominant, actually-firing signal |
| `contrast_score` | 1.0 (clipped ceiling) | **not** low — ruled out LOW_CONTRAST as the real cause |
| `blur_score` | 1.0 (clipped ceiling) | **not** blurry by this metric either |
| `angle_deg` | 2.5° | only 6/108 (5.6%) exceed 15° skew, and those 6 *also* have `char_estimate` near 0 |

**Conclusion, not assumption:** the task brief's example failure-reason
list includes `BAD_ANGLE` and `LOW_CONTRAST` as distinct categories. Both
were evaluated against this real data and found **not to be the actual
dominant cause** — contrast and blur scores are already high/good for
most OCCLUDED samples; the real signal is simply "too few character-
shaped pixels are present in the located plate region" (consistent with
small, distant, low-detail crops from wide-area camera footage). Adding
these as new top-level failure reasons would not have changed the
diagnostic picture and was **not done** — see
`ai/anpr/quality.py::PlateQuality.structured_result()`'s docstring for
where this was still added as a secondary "contributing factor" tag
(useful when a crop genuinely IS angle- or contrast-limited) without
claiming it explains this dataset's actual failures. This is the
"review, don't blindly tune" instruction applied concretely.

## 6. What this does and does not justify changing

**Not changed:** the 7-reason wire `failure_reason` taxonomy
(`ai/anpr/quality.py::FailureReason`) — already correctly explains every
observed failure on this data; adding categories that don't fire
meaningfully here would add noise, not clarity.

**Changed:** `PlateQuality.structured_result()` (Phase 18 Part B) — a
richer, multi-reason `{"quality": "LOW", "score": 31, "reasons": [...]}`
verdict for investigators/evaluators asking "why is this crop low
quality," listing every weak contributing factor rather than the one
canonical root cause. Additive; the wire schema is unchanged.

**Also changed:** `PlateTrackState.expired()` (Phase 18 Part C) — a real
bug (`now or time.time()` silently discarding a legitimate `0.0`
timestamp) found while testing the temporal-fusion layer this diagnostic
work depends on. See `docs/PHASE18_ANPR_DIAGNOSTICS.md`'s sibling commit
message / `ai/anpr/plate_track_state.py` for detail.

## 7. Honest limitations

- No fresh real-government-feed frame was captured in this session (both
  RTSP and HLS endpoints timed out) — REAL_HISTORICAL is a re-analysis of
  archived frames, not a live measurement.
- REAL_HISTORICAL's capture provenance (genuinely live vs. a substituted
  test source at the time) cannot be independently re-verified.
- Neither MOCK nor REAL_HISTORICAL has ground truth — their numbers are
  detection/failure-reason statistics, never "accuracy."
- SYNTHETIC accuracy numbers characterize pipeline wiring on
  out-of-distribution rendered text, never real-world ANPR performance.
- Sample sizes (30 / 62 / 136) are modest; a larger, repeated run would
  tighten these distributions further.
