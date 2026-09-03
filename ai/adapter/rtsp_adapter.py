import os
import cv2
import time
import logging
import numpy as np
from typing import Generator, Optional, Union, Dict, Any

from ai.adapter.frame_interface import FrameInput

logger = logging.getLogger("RTSPStreamAdapter")

class RTSPStreamAdapter:
    """
    Standalone video stream adapter for RTSP stream consumption and local video file testing.
    Provides decoded FrameInput objects to the Kavya AI pipeline without taking ownership of
    core production ingestion infrastructure.
    """

    def __init__(
        self,
        source: Union[str, int] = 0,
        camera_id: str = "CAM-001",
        frame_skip: int = 0,
        use_tcp: bool = True,
        max_reconnect_retries: int = 3,
        reconnect_backoff_sec: float = 1.0
    ):
        """
        :param source: RTSP URL (rtsp://...), video file path, or camera index integer.
        :param camera_id: Camera identifier associated with the stream.
        :param frame_skip: Number of frames to skip between processed frames (0 = process every frame).
        :param use_tcp: Force TCP transport for RTSP streams to eliminate UDP packet dropouts.
        :param max_reconnect_retries: Maximum reconnection attempts on stream interruption.
        :param reconnect_backoff_sec: Backoff delay in seconds between reconnection attempts.
        """
        self.source = source
        self.camera_id = camera_id
        self.frame_skip = max(0, frame_skip)
        self.use_tcp = use_tcp
        self.max_reconnect_retries = max_reconnect_retries
        self.reconnect_backoff_sec = reconnect_backoff_sec
        self.cap: Optional[cv2.VideoCapture] = None
        self.stream_start_time: float = time.time()

        if self.use_tcp and isinstance(self.source, str) and self.source.startswith("rtsp://"):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    def connect(self) -> bool:
        """Initialize OpenCV VideoCapture connection."""
        try:
            if isinstance(self.source, str) and self.source.isdigit():
                source_val = int(self.source)
            else:
                source_val = self.source

            self.cap = cv2.VideoCapture(source_val)
            if not self.cap.isOpened():
                logger.error(f"Failed to open video source: {self.source}")
                return False

            self.stream_start_time = time.time()
            logger.info(f"Successfully connected to video stream/source: {self.source}")
            return True
        except Exception as e:
            logger.error(f"Error opening video stream source '{self.source}': {e}")
            return False

    def stream_frames(
        self,
        max_frames: Optional[int] = None
    ) -> Generator[FrameInput, None, None]:
        """
        Generator yielding FrameInput objects from the video source.

        :param max_frames: Maximum total frames to yield before stopping (None = unconstrained).
        """
        if self.cap is None or not self.cap.isOpened():
            if not self.connect():
                return

        frame_count = 0
        yielded_count = 0
        consecutive_errors = 0

        while self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()

            if not ret or frame is None or frame.size == 0:
                consecutive_errors += 1
                logger.warning(
                    f"Read failure or empty frame from '{self.source}' "
                    f"(attempt {consecutive_errors}/{self.max_reconnect_retries})."
                )

                if consecutive_errors > self.max_reconnect_retries:
                    logger.info(f"Max reconnect attempts reached for '{self.source}'. Stopping generator.")
                    break

                # Backoff before retrying
                time.sleep(self.reconnect_backoff_sec)
                self.connect()
                continue

            # Reset error counter on successful frame read
            consecutive_errors = 0
            frame_count += 1

            # Frame sampling logic (frame_skip)
            if self.frame_skip > 0 and (frame_count - 1) % (self.frame_skip + 1) != 0:
                continue

            # Extract stream PTS (in msec)
            pos_msec = self.cap.get(cv2.CAP_PROP_POS_MSEC)
            pts = pos_msec if pos_msec > 0 else None

            # Calculate event timestamp derived from stream PTS + stream start wall time
            if pts is not None and pts > 0:
                frame_ts_sec = self.stream_start_time + (pts / 1000.0)
                frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(frame_ts_sec))
            else:
                frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Gather stream metadata
            height, width = frame.shape[:2]
            fps = self.cap.get(cv2.CAP_PROP_FPS)

            frame_input = FrameInput(
                frame=frame,
                camera_id=self.camera_id,
                pts=pts,
                timestamp=frame_timestamp,
                metadata={
                    "frame_index": frame_count,
                    "resolution": f"{width}x{height}",
                    "stream_fps": fps if fps > 0 else None,
                    "source": str(self.source)
                }
            )

            yield frame_input
            yielded_count += 1

            if max_frames and yielded_count >= max_frames:
                logger.info(f"Reached max_frames limit ({max_frames}). Stopping stream generator.")
                break

        self.close()

    def close(self) -> None:
        """Release video capture resource gracefully."""
        if self.cap:
            try:
                self.cap.release()
                logger.info(f"Released video capture source '{self.source}'.")
            except Exception as e:
                logger.warning(f"Error releasing video source: {e}")
            finally:
                self.cap = None
