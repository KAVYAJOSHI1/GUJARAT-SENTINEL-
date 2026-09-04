"""
scripts/tracking_demo.py

Demonstrates the three things DEVELOPER_README section 24 requires before PR:

  1. ByteTrack maintaining a persistent track ID across 100 continuous frames.
  2. The deduplication engine suppressing duplicate detections and emitting a
     single clean event payload when the vehicle leaves the camera view.
  3. The cross-camera trajectory builder sorting 4 sightings from 4 different
     cameras into chronological order.

Pure NumPy / SciPy -- no camera, GPU or OpenCV required:

    python scripts/tracking_demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.tracking.tracker import ByteTrackTracker, TrackEventDeduplicator
from ai.tracking.track_association import associate_plates_to_tracks
from ai.tracking.correlation import CrossCameraCorrelator


def _car(frame_idx, x0=120.0, y0=220.0, vx=4.0, w=90.0, h=64.0, score=0.92):
    x1 = x0 + vx * frame_idx
    return {"bbox": [x1, y0, x1 + w, y0 + h], "confidence": score, "class": "car"}


def demo_persistent_id():
    print("\n=== 1. Persistent track ID across 100 continuous frames ===")
    tracker = ByteTrackTracker()
    ids = set()
    for f in range(1, 101):
        out = tracker.update([_car(f)], frame_id=f)
        ids.add(out[0]["track_id"])
    final = out[0]
    print(f"  frames processed      : 100")
    print(f"  distinct track IDs    : {sorted(ids)}")
    print(f"  final track           : id={final['track_id']} hits={final['hits']} "
          f"bbox={[round(v, 1) for v in final['bbox']]}")
    assert ids == {1}, ids
    print("  PASS -- one stable camera-local ID for the whole pass.")


def demo_dedup_single_event():
    print("\n=== 2. Deduplication -> ONE consolidated event per completed track ===")
    tracker = ByteTrackTracker(track_buffer=5)
    dedup = TrackEventDeduplicator()
    raw_detections = 0
    emitted = []

    for f in range(1, 21):                       # vehicle in view for 20 frames
        online = tracker.update([_car(f)], frame_id=f)
        raw_detections += len(online)
    for f in range(21, 45):                      # vehicle gone -> track terminates
        tracker.update([], frame_id=f)
        for t in tracker.get_finalized_tracks():
            plate = associate_plates_to_tracks(
                [t], [{"bbox": [t["bbox"][0] + 25, t["bbox"][1] + 44,
                                t["bbox"][0] + 60, t["bbox"][1] + 60],
                       "plate_number": "GJ01AB1234", "confidence": 0.94}],
            )[t["track_id"]]
            if dedup.should_emit("cam05", t["track_id"], plate["plate_number"], f):
                emitted.append(dedup.build_event(t, "cam05", plate, timestamp=f,
                                                 location="05 Visat teen Rasta"))

    print(f"  per-frame online detections seen : {raw_detections}")
    print(f"  consolidated events emitted      : {len(emitted)}")
    print(json.dumps(emitted[0], indent=2, default=str))
    assert len(emitted) == 1
    print("  PASS -- 20 frames of detections collapsed to 1 event.")


def demo_cross_camera_trajectory():
    print("\n=== 3. Cross-camera trajectory: 4 cameras, inserted out of order ===")
    corr = CrossCameraCorrelator()
    sightings = [
        {"plate_number": "GJ01AB1234", "camera_id": "cam03", "location": "03 O.N.G.C. Office",
         "timestamp": "2026-09-03T09:15:00Z", "event_id": "e3"},
        {"plate_number": "GJ01AB1234", "camera_id": "cam01", "location": "01 Chiman bhai Bridge",
         "timestamp": "2026-09-03T09:00:00Z", "event_id": "e1"},
        {"plate_number": "GJ01AB1234", "camera_id": "cam05", "location": "05 Visat teen Rasta",
         "timestamp": "2026-09-03T09:25:00Z", "event_id": "e4"},
        {"plate_number": "GJ-01 AB 1234", "camera_id": "cam02", "location": "02 Janpath",
         "timestamp": "2026-09-03T09:10:00Z", "event_id": "e2"},
    ]
    print(f"  insertion order : {[s['camera_id'] for s in sightings]}")
    corr.add_events(sightings)
    traj = corr.build_trajectory("GJ01AB1234")
    print(f"  trajectory order: {[h['camera_id'] for h in traj]}")
    for h in traj:
        gap = h["seconds_since_previous"]
        gap_s = f"+{gap:.0f}s" if gap is not None else "start"
        print(f"    {h['timestamp']}  {h['camera_id']:>6}  {h['location']:<24} ({gap_s})")
    assert [h["camera_id"] for h in traj] == ["cam01", "cam02", "cam03", "cam05"]
    print("  PASS -- chronological ASC across all 4 cameras.")

    print("\n  vehicle-history payload (backend contract #4 shape):")
    print(json.dumps(corr.to_vehicle_history("GJ01AB1234", is_watchlisted=True), indent=2, default=str))


if __name__ == "__main__":
    demo_persistent_id()
    demo_dedup_single_event()
    demo_cross_camera_trajectory()
    print("\nAll three pre-PR demonstrations passed.\n")
