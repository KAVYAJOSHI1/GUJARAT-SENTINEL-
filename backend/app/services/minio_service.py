"""
MinIO S3-compatible object storage for evidence snapshots.
Initializes the `sentinel-evidence` bucket on startup and falls back to a
local disk folder transparently if MinIO is unreachable, per spec:
'MinIO Storage Unreachable -> Fallback to saving evidence snapshots to
local disk folder if MinIO service is offline.'
"""
import base64
import io
import logging
import os
import uuid
from datetime import datetime

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger("sentinel.minio")


class MinioService:
    def __init__(self):
        self._client: Minio | None = None
        self._bucket = settings.MINIO_BUCKET
        self._fallback_dir = settings.LOCAL_EVIDENCE_FALLBACK_DIR
        os.makedirs(self._fallback_dir, exist_ok=True)
        self._connect_and_ensure_bucket()

    def _connect_and_ensure_bucket(self) -> None:
        try:
            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            if not client.bucket_exists(self._bucket):
                client.make_bucket(self._bucket)
            self._client = client
            logger.info("MinIO bucket '%s' ready.", self._bucket)
        except Exception as exc:  # noqa: BLE001 — any connectivity issue -> fallback
            logger.warning("MinIO unreachable at startup (%s); using local fallback.", exc)
            self._client = None

    def _object_key(self, camera_id: str, plate: str, content_type: str) -> str:
        ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else "png"
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"{camera_id}/{ts}_{plate}_{uuid.uuid4().hex[:8]}.{ext}"

    def upload_snapshot(
        self, camera_id: str, plate: str, snapshot_base64: str, content_type: str = "image/jpeg"
    ) -> str:
        """Returns a URL/path reference to the stored snapshot. Never raises."""
        raw = base64.b64decode(snapshot_base64)
        key = self._object_key(camera_id, plate, content_type)

        if self._client is not None:
            try:
                self._client.put_object(
                    self._bucket,
                    key,
                    data=io.BytesIO(raw),
                    length=len(raw),
                    content_type=content_type,
                )
                scheme = "https" if settings.MINIO_SECURE else "http"
                return f"{scheme}://{settings.MINIO_ENDPOINT}/{self._bucket}/{key}"
            except S3Error as exc:
                logger.warning("MinIO upload failed (%s); falling back to local disk.", exc)

        # --- Local disk fallback ---
        local_path = os.path.join(self._fallback_dir, key.replace("/", "_"))
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(raw)
        return f"file://{os.path.abspath(local_path)}"


_minio_service: MinioService | None = None


def get_minio_service() -> MinioService:
    global _minio_service
    if _minio_service is None:
        _minio_service = MinioService()
    return _minio_service
