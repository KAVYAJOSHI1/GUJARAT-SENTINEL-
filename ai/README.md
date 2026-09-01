# SENTINEL AI Analytics Subsystem

Owners: **Kavya** (Detection + ANPR/OCR) & **Prajin** (Tracking + Correlation)
Branches: `feature/kavya-ai-anpr` / `feature/prajin-tracking`

## Pipeline Structure
```text
Video Frame -> YOLO Detection -> ByteTrack Tracking -> Plate Detection -> OCR -> Event Generation
```

## Subdirectories
- `detection/`: Pretrained YOLO detector for vehicles and pedestrians
- `anpr/`: License plate locator & cropper
- `ocr/`: PaddleOCR / multi-frame consensus OCR
- `tracking/`: ByteTrack object tracker & cross-camera identity engine
