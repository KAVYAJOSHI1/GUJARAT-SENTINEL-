# SENTINEL — AI Analytics & ANPR/OCR Pipeline Architecture

> **Phase 12 (AI intelligence layer — Copilot / NL search / AI summaries /
> stopped-vehicle anomaly)** is documented separately in
> [`docs/AI_ARCHITECTURE.md`](docs/AI_ARCHITECTURE.md),
> [`docs/AI_INVESTIGATION_COPILOT.md`](docs/AI_INVESTIGATION_COPILOT.md),
> [`docs/AI_SEARCH.md`](docs/AI_SEARCH.md),
> [`docs/AI_BEHAVIOR_ANALYTICS.md`](docs/AI_BEHAVIOR_ANALYTICS.md) and
> [`docs/AI_DEMO_RUNBOOK.md`](docs/AI_DEMO_RUNBOOK.md). This file covers the
> detection / ANPR / OCR / tracking pipeline it reads from.

---

## 1. Overview
The AI Analytics Subsystem extracts high-accuracy vehicle registration numbers from multi-camera video streams under varying lighting, motion, and environmental conditions.

---

## 2. Multi-Stage AI Inference Pipeline

```text
[ Input Frame Buffer ]
          │
          ▼
1. YOLOv8 Vehicle Detector ──► [ Vehicle Bounding Box (car, truck, bus) ]
          │
          ▼
2. License Plate Locator   ──► [ Sub-Image Crop of License Plate Region ]
          │
          ▼
3. Preprocessing Engine    ──► Grayscale + CLAHE Contrast + Adaptive Threshold
          │
          ▼
4. EasyOCR Text Engine     ──► Character Detection & Text Recognition
          │
          ▼
5. Plate Normalization     ──► Regex Strip Spaces/Hyphens (e.g. GJ-01 AB 1234 -> GJ01AB1234)
          │
          ▼
6. Consensus Voting        ──► Frequency Aggregator across 10 Track Frames
          │
          ▼
[ Final AI Detection Event Payload ]
```

---

## 3. Key Pipeline Components

- **YOLOv8 Nano (`yolov8n.pt`)**: Pretrained model detecting vehicles at $\ge 0.50$ confidence threshold.
- **Contrast Limited Adaptive Histogram Equalization (CLAHE)**: Enhances local image contrast in low-light and high-glare environments prior to OCR.
- **EasyOCR Engine** (default; PaddleOCR optional via `OCR_ENGINE=paddleocr`): Extracts alphanumeric text strings and confidence metrics.
- **Multi-Frame Consensus Voting**: Stores predictions across sequential frames of a ByteTrack object track. Emits majority vote plate string, eliminating isolated single-frame character misreads.
