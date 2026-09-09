"""
ai/regions.py

Phase 17 Step 6 -- camera sharding / regional simulation.

HONESTY NOTE (read before using this anywhere near a demo): this is an
ARCHITECTURAL SIMULATION, not a distributed deployment. There is no
Kubernetes, no cross-host orchestration, no network boundary between
"regions" here -- this module only provides a deterministic, explainable
way to group camera_ids into named regions and assign each region a
number of AI workers, so the resulting structure can be presented as:

    Central control plane
            |
            +---- Ahmedabad region  -- N workers
            +---- Surat region      -- N workers
            +---- Rajkot region     -- N workers
            +---- Vadodara region   -- N workers
            +---- Other region      -- N workers

...while being completely explicit that today's actual runtime is a
single-process (or single-host multi-process, see ai/worker_pool.py)
pipeline. Every function/return value in this module is labeled
"SIMULATED" wherever it is surfaced (capacity API, docs) -- never
presented as measured or deployed infrastructure.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# A small, named set of regions matching Gujarat's major CCTV-density
# cities plus a catch-all -- illustrative grouping, not a population/camera
# census. Swap REGION_NAMES for a real district list when actual regional
# camera density figures are available (see docs/SCALE_TO_80000.md).
REGION_NAMES: List[str] = ["ahmedabad", "surat", "rajkot", "vadodara", "other"]


def camera_region(camera_id: str, num_regions: int = len(REGION_NAMES)) -> str:
    """Deterministic, stable camera -> region assignment (crc32, never
    Python's randomized hash() -- same reasoning as
    ai.worker_pool.camera_worker_index: must be stable across processes)."""
    idx = zlib.crc32(camera_id.encode("utf-8")) % max(1, num_regions)
    return REGION_NAMES[idx] if idx < len(REGION_NAMES) else REGION_NAMES[-1]


@dataclass
class RegionAssignment:
    region: str
    camera_ids: List[str] = field(default_factory=list)
    worker_ids: List[int] = field(default_factory=list)


def regional_topology(
    camera_ids: List[str],
    *,
    workers_per_region: int = 2,
    region_names: Optional[List[str]] = None,
) -> Dict[str, RegionAssignment]:
    """SIMULATED regional topology: groups the given camera_ids by region
    (deterministic hash) and assigns each region a fixed number of
    (also simulated) worker ids, disjoint across regions -- purely for
    presenting a "central control plane -> regions -> workers" picture
    consistent with ai.worker_pool's real deterministic-sharding approach,
    scaled up conceptually. No process, thread, or network resource is
    created by calling this function."""
    names = region_names or REGION_NAMES
    topo: Dict[str, RegionAssignment] = {r: RegionAssignment(region=r) for r in names}
    for cam_id in camera_ids:
        r = camera_region(cam_id, len(names))
        topo[r].camera_ids.append(cam_id)

    next_worker_id = 0
    for r in names:
        topo[r].worker_ids = list(range(next_worker_id, next_worker_id + workers_per_region))
        next_worker_id += workers_per_region

    return topo


def topology_summary(topo: Dict[str, RegionAssignment]) -> Dict[str, object]:
    return {
        "label": "SIMULATED -- architectural grouping only, not a distributed deployment",
        "regions": {
            r: {
                "camera_count": len(a.camera_ids),
                "camera_ids": a.camera_ids,
                "worker_ids": a.worker_ids,
                "worker_count": len(a.worker_ids),
            }
            for r, a in topo.items()
        },
        "total_cameras": sum(len(a.camera_ids) for a in topo.values()),
        "total_workers": sum(len(a.worker_ids) for a in topo.values()),
    }
