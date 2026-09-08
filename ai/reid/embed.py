"""
Pipeline-side vehicle appearance embedder (Phase 15E).

The AI pipeline container HAS torch (ultralytics pulls it). When
``SENTINEL_REID_EMBED=1`` this computes a real CNN embedding on each
vehicle crop and the pipeline attaches it to the detection event
(``event["embedding"]``); the backend stores it verbatim in
``vehicle_embeddings`` (source "pipeline") instead of the deterministic
attribute baseline.

Lightweight by default (MobileNetV3-Small, ~2.5M params, fine on CPU),
ResNet-50 optional via ``SENTINEL_REID_MODEL=resnet50``. GPU when
available. Embeddings are L2-normalised. Fails soft: any error -> the
embedder disables itself and the pipeline sends no embedding (backend
falls back to the attribute baseline).
"""
from __future__ import annotations

import logging
import math
import os
from typing import List, Optional

logger = logging.getLogger("ai.reid.embed")

_MODELS = {
    "mobilenet_v3_small": ("torch-mobilenetv3s-imagenet", 576),
    "resnet50": ("torch-resnet50-imagenet", 2048),
}


def _l2(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 1e-12 else [0.0] * len(v)


class VehicleEmbedder:
    def __init__(self, model_key: Optional[str] = None, enabled: Optional[bool] = None):
        self.enabled = (
            enabled if enabled is not None
            else os.getenv("SENTINEL_REID_EMBED", "0").strip().lower() in ("1", "true", "yes", "on")
        )
        self.model_key = (model_key or os.getenv("SENTINEL_REID_MODEL", "mobilenet_v3_small")).strip()
        if self.model_key not in _MODELS:
            self.model_key = "mobilenet_v3_small"
        self.model_name, self.dim = _MODELS[self.model_key]
        self.device = "cpu"
        self._model = None
        self._preprocess = None
        self._torch = None
        self._failed = False

    # ------------------------------------------------------------------ #
    def _ensure(self) -> bool:
        if self._model is not None:
            return True
        if self._failed or not self.enabled:
            return False
        try:
            import torch
            from torchvision import models as tvm

            self._torch = torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            if self.model_key == "resnet50":
                w = tvm.ResNet50_Weights.IMAGENET1K_V2
                net = tvm.resnet50(weights=w)
                net.fc = torch.nn.Identity()
            else:
                w = tvm.MobileNet_V3_Small_Weights.IMAGENET1K_V1
                net = tvm.mobilenet_v3_small(weights=w)
                net.classifier = torch.nn.Identity()
            net.eval().to(self.device)
            self._model = net
            self._preprocess = w.transforms()
            logger.info("VehicleEmbedder ready: %s on %s (dim %d)",
                        self.model_name, self.device, self.dim)
            return True
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            logger.warning("VehicleEmbedder disabled (%s)", exc)
            return False

    def embed_bgr(self, crop_bgr) -> Optional[List[float]]:
        """crop_bgr: an OpenCV BGR numpy array. Returns an L2-normalised
        list[float] or None (disabled / failed / bad input)."""
        if not self._ensure() or crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
            return None
        try:
            import numpy as np
            from PIL import Image

            rgb = crop_bgr[:, :, ::-1] if crop_bgr.ndim == 3 else crop_bgr
            img = Image.fromarray(np.ascontiguousarray(rgb).astype("uint8")).convert("RGB")
            with self._torch.no_grad():
                batch = self._preprocess(img).unsqueeze(0).to(self.device)
                feat = self._model(batch).flatten().cpu().tolist()
            return _l2(feat)
        except Exception as exc:  # noqa: BLE001
            logger.debug("embed failed: %s", exc)
            return None

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "loaded": self._model is not None,
            "failed": self._failed,
            "model": self.model_name,
            "device": self.device,
            "dim": self.dim,
        }
