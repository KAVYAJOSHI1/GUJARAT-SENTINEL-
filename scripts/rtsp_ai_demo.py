#!/usr/bin/env python3
"""
GUJARAT SENTINEL 2026 — Live RTSP AI / ANPR Pipeline Integration Demo

Standalone demonstration runner connecting to an RTSP stream (or video file),
extracting decoded video frames, feeding them to Kavya's AI/ANPR pipeline,
and printing real-time detection events and performance benchmarks.

Usage:
  python scripts/rtsp_ai_demo.py --source "rtsp://localhost:8554/stream/cam1" --camera-id "CAM-GANDHINAGAR-01"
  python scripts/rtsp_ai_demo.py --source "sample_video.mp4" --frame-skip 2
"""

import os
import sys
import time
import json
import argparse
import logging
from typing import Optional

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.adapter.rtsp_adapter import RTSPStreamAdapter
from ai.pipeline import AIPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("RTSP_AI_Demo")

def main():
    parser = argparse.ArgumentParser(description="SENTINEL AI/ANPR RTSP Stream Integration Demo")
    parser.add_argument(
        "--source",
        type=str,
        default=os.getenv("SENTINEL_RTSP_URL", os.getenv("RTSP_URL", "")),
        help="RTSP stream URL (rtsp://...), local video file path (.mp4), or camera device index (0)."
    )
    parser.add_argument(
        "--camera-id",
        type=str,
        default=os.getenv("CAMERA_ID", "CAM-SENTINEL-01"),
        help="Camera identifier (default: CAM-SENTINEL-01 or CAMERA_ID env var)."
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=int(os.getenv("FRAME_SKIP", "0")),
        help="Number of frames to skip between processed frames (default: 0)."
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=float(os.getenv("CONFIDENCE_THRESHOLD", "0.50")),
        help="Minimum vehicle detection confidence threshold (default: 0.50)."
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=int(os.getenv("MAX_FRAMES", "300")),
        help="Maximum total frames to stream during test run (default: 300)."
    )
    parser.add_argument(
        "--evidence-dir",
        type=str,
        default=os.getenv("SENTINEL_EVIDENCE_DIR", "evidence/rtsp_demo"),
        help="Directory to save snapshot and plate crop evidence."
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default=os.getenv("SENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/events/ai-detection"),
        help="Backend AI detection event ingestion endpoint URL."
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Print detailed latency and throughput benchmark summary upon exit."
    )

    args = parser.parse_args()

    print("=================================================================")
    print("      GUJARAT SENTINEL 2026 — RTSP AI / ANPR DEMO RUNNER        ")
    print("=================================================================")
    print(f" • Source: {args.source if args.source else '[None specified - running synthetic mode]'}")
    print(f" • Camera ID: {args.camera_id}")
    print(f" • Frame Skip: {args.frame_skip}")
    print(f" • Confidence Threshold: {args.confidence_threshold}")
    print(f" • Evidence Directory: {args.evidence_dir}")
    print("=================================================================\n")

    # Initialize AI Pipeline
    pipeline = AIPipeline(
        backend_url=args.backend_url,
        evidence_dir=args.evidence_dir,
        confidence_threshold=args.confidence_threshold,
        device="cpu"
    )

    # If no source provided or source does not exist, log info and run synthetic test mode
    source_val = args.source
    if not source_val:
        print("[!] No RTSP stream URL or video source supplied via --source or SENTINEL_RTSP_URL environment variable.")
        print("[!] To run against a live stream or file, execute:")
        print("    python scripts/rtsp_ai_demo.py --source \"rtsp://<host>:8554/stream/<id>\"\n")
        print("[*] Generating synthetic stream test frames for local demonstration...")
        _run_synthetic_demo(pipeline, args.camera_id)
        return

    # Initialize Stream Adapter
    adapter = RTSPStreamAdapter(
        source=source_val,
        camera_id=args.camera_id,
        frame_skip=args.frame_skip,
        use_tcp=True
    )

    if not adapter.connect():
        print(f"[X] Failed to connect to stream source '{source_val}'.")
        print("    Ensure the stream URL or file path is valid and accessible.")
        sys.exit(1)

    print(f"[✓] Streaming from source: {source_val}")
    print("Press Ctrl+C to terminate stream processing.\n")

    total_events = 0
    t0_stream = time.time()

    try:
        for frame_input in adapter.stream_frames(max_frames=args.max_frames):
            events = pipeline.process_frame(frame_input)
            if events:
                for evt in events:
                    total_events += 1
                    veh = evt["vehicle"]
                    plate = evt["license_plate"]
                    ev = evt["evidence"]

                    print("-----------------------------------------------------------------")
                    print(f" [AI EVENT DETECTED #{total_events}]")
                    print(f"  • Event ID:        {evt['event_id']}")
                    print(f"  • Camera ID:       {evt['camera_id']}")
                    print(f"  • Timestamp:       {evt['timestamp']} (PTS: {evt.get('pts')})")
                    print(f"  • Vehicle Class:   {veh['type']} (conf: {veh['confidence']:.2f})")
                    print(f"  • Bounding Box:    {veh['bbox']}")
                    print(f"  • Recognized Plate:{plate['text']} (conf: {plate['confidence']:.2f})")
                    print(f"  • Consensus Used:  {plate['consensus_applied']} (reads: {plate.get('raw_reads', [])})")
                    print(f"  • Frame Snapshot:  {ev['frame_path']}")
                    print(f"  • Plate Crop:      {ev['plate_crop_path']}")
                    print("-----------------------------------------------------------------")

    except KeyboardInterrupt:
        print("\n[!] Stream processing interrupted by user.")
    finally:
        adapter.close()

    elapsed = time.time() - t0_stream
    print("\n=================================================================")
    print("                   STREAM SUMMARY & BENCHMARK                    ")
    print("=================================================================")
    stats = pipeline.get_benchmark_stats()
    print(f" • Total Elapsed Run Time:     {elapsed:.2f} s")
    print(f" • Total Stream Frames Received: {stats['total_frames_received']}")
    print(f" • Processed Frames:            {stats['processed_frames']}")
    print(f" • Vehicles Detected:           {stats['total_vehicles_detected']}")
    print(f" • AI Events Generated:         {stats['total_ai_events_generated']}")
    print(f" • Avg Vehicle Detection Time:  {stats['avg_vehicle_detection_ms']} ms")
    print(f" • Avg OCR Latency per Vehicle: {stats['avg_ocr_ms']} ms")
    print(f" • Avg Total Pipeline Latency:  {stats['avg_pipeline_latency_ms']} ms")
    print(f" • Estimated AI Throughput:     {stats['estimated_fps']} FPS")
    print("=================================================================")

def _run_synthetic_demo(pipeline: AIPipeline, camera_id: str):
    """Fallback runner using synthetic frame matrix when no stream URL is specified."""
    import numpy as np
    import cv2

    print("Executing synthetic frame demonstration...")
    dummy_frame = np.random.randint(50, 200, (720, 1280, 3), dtype=np.uint8)
    
    # Process synthetic frame
    events = pipeline.process_frame(dummy_frame, camera_id=camera_id)
    
    stats = pipeline.get_benchmark_stats()
    print("\n[✓] Synthetic Benchmark Run Completed:")
    print(json.dumps(stats, indent=2))
    print("\nSample Generated Payload Structure:")
    sample_evt = {
        "event_id": "evt_demo123456",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pts": 1234.56,
        "camera_id": camera_id,
        "vehicle": {
            "type": "car",
            "class": "car",
            "confidence": 0.94,
            "bbox": [100, 150, 500, 450],
            "track_id": 1
        },
        "license_plate": {
            "text": "GJ01AB1234",
            "plate_number": "GJ01AB1234",
            "confidence": 0.95,
            "bbox": [200, 350, 400, 410],
            "raw_text": "GJ01AB1234",
            "consensus_applied": True,
            "raw_reads": ["GJ01AB1234"]
        },
        "evidence": {
            "frame_path": f"evidence/rtsp_demo/{camera_id}_1725273200_tr1_GJ01AB1234.jpg",
            "frame_snapshot_path": f"evidence/rtsp_demo/{camera_id}_1725273200_tr1_GJ01AB1234.jpg",
            "plate_crop_path": f"evidence/rtsp_demo/{camera_id}_1725273200_tr1_GJ01AB1234_crop.jpg"
        }
    }
    print(json.dumps(sample_evt, indent=2))

if __name__ == "__main__":
    main()
