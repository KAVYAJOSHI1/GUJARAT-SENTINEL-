# SENTINEL — Hardware Sizing & Infrastructure Specifications

---

## 1. PoC Environment Sizing (~50 Camera Streams)

- **CPU**: 16 vCPU cores (Intel Xeon / AMD EPYC @ 2.8 GHz+)
- **GPU**: 1x NVIDIA RTX 4090 / T4 Tensor Core GPU (16GB VRAM) for YOLOv8 & EasyOCR inference
- **RAM**: 32 GB DDR4
- **Storage**: 1 TB NVMe SSD (PostgreSQL + MinIO snapshot storage buffer)
- **Network Bandwidth**: 100 Mbps dedicated uplink for multi-stream RTSP/TCP ingestion

---

## 2. Resource Allocation per Ingestion Thread

- **Stream Ingestion Thread**: ~100 MB RAM, $< 2\%$ CPU utilization per active stream.
- **YOLO + EasyOCR Pipeline**: ~2.5 GB VRAM allocated for model weight weights and frame batching.
