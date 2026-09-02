import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import numpy as np

@dataclass
class FrameInput:
    """
    Standardized data container for decoded video frames passed from
    upstream CCTV ingestion components to the Kavya AI/ANPR pipeline.
    """
    frame: np.ndarray
    camera_id: str = "CAM-001"
    pts: Optional[float] = None  # Presentation timestamp (in seconds or msec from stream demuxer)
    timestamp: Optional[str] = None  # Explicit ISO 8601 string or UNIX timestamp
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def get_event_timestamp(self) -> str:
        """
        Derives the primary CCTV event timestamp.
        Uses explicit timestamp string if provided, or converts PTS, or falls back to UTC system time.
        """
        if self.timestamp and isinstance(self.timestamp, str) and self.timestamp.strip():
            return self.timestamp.strip()

        if self.pts is not None:
            try:
                pts_val = float(self.pts)
                # If PTS is a UNIX timestamp in milliseconds
                if pts_val > 1e11:
                    t_sec = pts_val / 1000.0
                    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_sec))
                # If PTS is a UNIX timestamp in seconds
                elif pts_val > 1e8:
                    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pts_val))
            except (ValueError, TypeError):
                pass

        # Fallback to current UTC system time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
