"""
Vehicle Visual Re-ID (Phase 14 §1).

    detection -> crop -> appearance features -> embedding
              -> bounded vector similarity search -> candidate matches
              -> cross-camera correlation (Phase 14 §2)

`VehicleReIDService` is the public surface:

    extract_embedding(event)     -> unit vector for one sighting
    index_event(event)           -> upsert its vehicle_embeddings row (idempotent)
    backfill(limit)              -> index events that have no embedding yet
    compare(event_a, event_b)    -> {similarity, band, confidence, ...}
    find_similar(event|embedding)-> ranked candidate list (bounded)
    rank_candidates(vec, rows)   -> sorted [(row, similarity)]

Embedding backends are pluggable (like the LLM provider):

  * AttributeEmbeddingBackend -- deterministic, zero ML deps. THE DEFAULT.
    Vector = weighted [ type one-hot | colour one-hot | plate-known |
    confidence | stable texture signature ], L2-normalised. Identical plate
    strings -> identical vector; same type+colour -> close; different -> far.
  * TorchReIDBackend -- ResNet-50 features on the crop. Constructed only if
    torch + torchvision import (AI pipeline env). Never required here.

IMPORTANT: visual similarity is NOT identity. `_band()` never returns a
"confirmed" verdict; only a plate match (handled by the correlation layer)
can do that.
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Iterable, Optional

from sqlalchemy import select
from sqlmodel import Session

from app.config import settings
from app.models.base import ConfidenceLevel
from app.models.camera import Camera
from app.models.vehicle_embedding import VehicleEmbedding
from app.models.vehicle_event import VehicleEvent

logger = logging.getLogger("sentinel.ai.reid")

# ---- fixed vocabularies (order is the vector layout -- never reorder) ----
_TYPE_VOCAB = (
    "car", "motorcycle", "bus", "truck", "bicycle", "auto-rickshaw", "_other",
)
_COLOR_VOCAB = (
    "white", "black", "silver", "grey", "gray", "red", "blue", "green",
    "yellow", "brown", "orange", "_other",
)
_TEXTURE_DIM = 8

_TYPE_WEIGHT = 3.0
_COLOR_WEIGHT = 2.5
_META_WEIGHT = 0.6
# Texture is the "which specific object" signal. Weighted so that two
# vehicles of the SAME type + colour but different identity land around
# MODERATE (a lead), never STRONG -- only an exact plate match is "same".
_TEXTURE_WEIGHT = 1.0

ATTRIBUTE_MODEL_NAME = "attr-baseline-v1"


# --------------------------------------------------------------------------- #
#  vector maths (pure python -- the backend image has no numpy)
# --------------------------------------------------------------------------- #
def _l2_normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if n <= 1e-12:
        return [0.0] * len(v)
    return [x / n for x in v]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Both are expected unit vectors -> dot product. Robust to length
    mismatch (compares the shared prefix) and to non-normalised input."""
    if not a or not b:
        return 0.0
    m = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(m))
    na = math.sqrt(sum(a[i] * a[i] for i in range(m)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(m)))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _texture_signature(seed: str, dim: int = _TEXTURE_DIM) -> list[float]:
    """A stable pseudo-random unit-ish vector in [-1, 1]^dim derived from a
    seed string. Deterministic: same seed -> same vector. Absent a real CNN
    this encodes 'which specific object' -- the plate string is the best
    identity signal we have, so two sightings of the same plate share it
    exactly, while same-type/same-colour different vehicles still separate.
    """
    out: list[float] = []
    i = 0
    while len(out) < dim:
        h = hashlib.sha256(f"{seed}|{i}".encode()).digest()
        for j in range(0, len(h), 2):
            if len(out) >= dim:
                break
            val = int.from_bytes(h[j:j + 2], "big") / 65535.0  # [0,1]
            out.append(val * 2.0 - 1.0)                          # [-1,1]
        i += 1
    return out


def _one_hot(value: Optional[str], vocab: tuple[str, ...]) -> list[float]:
    vec = [0.0] * len(vocab)
    key = (value or "").strip().lower()
    if key in vocab:
        vec[vocab.index(key)] = 1.0
    else:
        vec[vocab.index("_other")] = 1.0
    return vec


# --------------------------------------------------------------------------- #
#  embedding backends
# --------------------------------------------------------------------------- #
class EmbeddingBackend:
    name: str = "base"
    dim: int = 0

    def extract(self, features: dict) -> list[float]:  # pragma: no cover - abstract
        raise NotImplementedError


class AttributeEmbeddingBackend(EmbeddingBackend):
    """Deterministic, dependency-free appearance embedding.

    `features` keys used: vehicle_type, vehicle_color, plate_number_normalized,
    confidence_score. Missing keys degrade gracefully (never raises).
    """

    name = ATTRIBUTE_MODEL_NAME
    dim = len(_TYPE_VOCAB) + len(_COLOR_VOCAB) + 2 + _TEXTURE_DIM

    def extract(self, features: dict) -> list[float]:
        vtype = features.get("vehicle_type")
        color = features.get("vehicle_color")
        plate = (features.get("plate_number_normalized") or "").strip().upper()
        conf = features.get("confidence_score")

        type_block = [x * _TYPE_WEIGHT for x in _one_hot(vtype, _TYPE_VOCAB)]
        color_block = [x * _COLOR_WEIGHT for x in _one_hot(color, _COLOR_VOCAB)]

        plate_known = 1.0 if plate and plate != "UNKNOWN" else 0.0
        conf_val = float(conf) if isinstance(conf, (int, float)) else 0.5
        meta_block = [plate_known * _META_WEIGHT, conf_val * _META_WEIGHT]

        # texture seed: the plate when we have one (same vehicle -> identical),
        # else a per-track/per-camera fallback so unknowns still separate.
        if plate_known:
            seed = f"plate:{plate}"
        else:
            seed = "track:{}:{}".format(
                features.get("camera_code") or features.get("camera_id") or "?",
                features.get("track_id"),
            )
        texture_block = [x * _TEXTURE_WEIGHT for x in _texture_signature(seed)]

        return _l2_normalise(type_block + color_block + meta_block + texture_block)


# torchvision backbones we support, smallest first. Licensing: all are
# BSD-3 (torchvision) with ImageNet-pretrained weights -- no bespoke Re-ID
# dataset / model, no from-scratch training.
_TORCH_MODELS = {
    "mobilenet_v3_small": ("torch-mobilenetv3s-imagenet", 576),
    "resnet50": ("torch-resnet50-imagenet", 2048),
}


class TorchEmbeddingBackend(EmbeddingBackend):  # pragma: no cover - optional path
    """Penultimate CNN features on a vehicle crop (a re-identification-
    compatible embedding). Uses an ImageNet-pretrained torchvision backbone
    -- lightweight by default (MobileNetV3-Small), ResNet-50 optional. GPU
    when available, CPU otherwise. Only constructible where torch +
    torchvision + PIL import; the backend API silently falls back to the
    attribute baseline elsewhere.

    Embeddings are L2-normalised. Visual similarity is still NOT identity.
    """

    def __init__(self, model_key: Optional[str] = None) -> None:
        import torch
        import torchvision  # noqa: F401
        from PIL import Image  # noqa: F401

        model_key = (model_key or settings.REID_TORCH_MODEL or "mobilenet_v3_small").strip()
        if model_key not in _TORCH_MODELS:
            model_key = "mobilenet_v3_small"
        self.name, self.dim = _TORCH_MODELS[model_key]
        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        from torchvision import models as tvm
        if model_key == "resnet50":
            weights = tvm.ResNet50_Weights.IMAGENET1K_V2
            net = tvm.resnet50(weights=weights)
            net.fc = torch.nn.Identity()
        else:
            weights = tvm.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            net = tvm.mobilenet_v3_small(weights=weights)
            net.classifier = torch.nn.Identity()
        net.eval().to(self.device)
        self._model = net
        self._preprocess = weights.transforms()
        self.model_key = model_key
        logger.info("TorchEmbeddingBackend ready: %s on %s (dim %d)",
                    self.name, self.device, self.dim)

    def extract(self, features: dict) -> list[float]:
        from io import BytesIO

        import numpy as _np
        from PIL import Image

        raw = features.get("crop_bytes")
        arr = features.get("crop_array")
        if raw:
            img = Image.open(BytesIO(raw)).convert("RGB")
        elif arr is not None:
            a = _np.asarray(arr)
            if a.ndim == 3 and a.shape[2] == 3:      # assume BGR from OpenCV
                a = a[:, :, ::-1]
            img = Image.fromarray(a.astype("uint8")).convert("RGB")
        else:
            raise ValueError("TorchEmbeddingBackend needs features['crop_bytes'] or ['crop_array']")
        with self._torch.no_grad():
            batch = self._preprocess(img).unsqueeze(0).to(self.device)
            feat = self._model(batch).flatten().cpu().tolist()
        return _l2_normalise(feat)


# back-compat alias (Phase 14 name)
TorchReIDBackend = TorchEmbeddingBackend


_BACKEND_CACHE: dict[str, EmbeddingBackend] = {}


_BACKEND_STATUS: dict = {"requested": None, "active": None, "fell_back": False, "reason": None}


def _requested_backend_name() -> str:
    # REID_BACKEND is the Phase 15 name; REID_EMBEDDING_BACKEND is the
    # Phase 14 name. REID_BACKEND wins when explicitly set to non-default.
    b15 = (getattr(settings, "REID_BACKEND", "") or "").strip().lower()
    if b15 and b15 != "attribute":
        return b15
    return (settings.REID_EMBEDDING_BACKEND or b15 or "attribute").strip().lower()


def get_embedding_backend(name: Optional[str] = None) -> EmbeddingBackend:
    name = (name or _requested_backend_name() or "attribute").strip().lower()
    _BACKEND_STATUS["requested"] = name
    if name in _BACKEND_CACHE:
        _BACKEND_STATUS["active"] = _BACKEND_CACHE[name].name
        return _BACKEND_CACHE[name]
    backend: EmbeddingBackend
    if name == "torch":
        try:
            backend = TorchEmbeddingBackend()
            _BACKEND_STATUS.update(fell_back=False, reason=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("torch Re-ID backend unavailable (%s) -- using attribute baseline", exc)
            backend = AttributeEmbeddingBackend()
            _BACKEND_STATUS.update(fell_back=True, reason=f"torch unavailable: {exc}")
    else:
        backend = AttributeEmbeddingBackend()
        _BACKEND_STATUS.update(fell_back=False, reason=None)
    _BACKEND_STATUS["active"] = backend.name
    _BACKEND_CACHE[name] = backend
    return backend


def reid_backend_status() -> dict:
    """For GET /ai/reid/status."""
    be = get_embedding_backend()
    device = getattr(be, "device", "cpu")
    return {
        "requested_backend": _requested_backend_name(),
        "active_backend": "torch" if isinstance(be, TorchEmbeddingBackend) else "attribute",
        "model": be.name,
        "device": device,
        "loaded": True,
        "fell_back_to_attribute": _BACKEND_STATUS.get("fell_back", False),
        "fallback_reason": _BACKEND_STATUS.get("reason"),
        "embedding_dimension": be.dim,
        "candidate_limit": settings.REID_MAX_CANDIDATES,
        "similarity_thresholds": {
            "strong": settings.REID_SIMILARITY_STRONG,
            "moderate": settings.REID_SIMILARITY_MODERATE,
            "weak": settings.REID_SIMILARITY_WEAK,
        },
        "note": (
            "Visual similarity is not identity. The torch backbone is an "
            "ImageNet-pretrained torchvision model (no bespoke Re-ID training); "
            "it activates only where torch/torchvision/PIL import."
        ),
    }


# --------------------------------------------------------------------------- #
#  similarity bands  (visual similarity is NOT identity)
# --------------------------------------------------------------------------- #
def similarity_band(score: float) -> tuple[str, ConfidenceLevel]:
    """Map a cosine score to a human band + a CAPPED confidence. The service
    never returns HIGH from visual similarity alone -- only the correlation
    layer, with a plate match, can escalate past MEDIUM."""
    if score >= settings.REID_SIMILARITY_STRONG:
        return "STRONG", ConfidenceLevel.MEDIUM
    if score >= settings.REID_SIMILARITY_MODERATE:
        return "MODERATE", ConfidenceLevel.LOW
    if score >= settings.REID_SIMILARITY_WEAK:
        return "WEAK", ConfidenceLevel.LOW
    return "NONE", ConfidenceLevel.INSUFFICIENT


# --------------------------------------------------------------------------- #
#  service
# --------------------------------------------------------------------------- #
class VehicleReIDService:
    def __init__(self, db: Session, *, backend: Optional[EmbeddingBackend] = None):
        self.db = db
        self.backend = backend or get_embedding_backend()

    # ---- feature extraction ---------------------------------------------- #
    @staticmethod
    def _features(event: VehicleEvent) -> dict:
        return {
            "vehicle_type": event.vehicle_type,
            "vehicle_color": event.vehicle_color,
            "plate_number_normalized": event.plate_number_normalized,
            "confidence_score": event.confidence_score,
            "camera_code": event.camera_code,
            "camera_id": event.camera_id,
            "track_id": event.track_id,
        }

    def extract_embedding(self, event: VehicleEvent) -> list[float]:
        return self.backend.extract(self._features(event))

    # ---- indexing ------------------------------------------------------- #
    def index_event(
        self,
        event: VehicleEvent,
        *,
        precomputed: Optional[list[float]] = None,
        source: Optional[str] = None,
    ) -> VehicleEmbedding:
        """Upsert the embedding row for one event. Idempotent on
        vehicle_event_id. Commits."""
        existing = self.db.execute(
            select(VehicleEmbedding).where(
                VehicleEmbedding.vehicle_event_id == event.id
            )
        ).scalar_one_or_none()

        if precomputed:
            vec = _l2_normalise([float(x) for x in precomputed])
            model_name = source or "pipeline"
            src = source or "pipeline"
        else:
            vec = self.extract_embedding(event)
            model_name = self.backend.name
            src = "attribute" if isinstance(self.backend, AttributeEmbeddingBackend) else "torch"

        if existing:
            existing.embedding = vec
            existing.dim = len(vec)
            existing.model_name = model_name
            existing.source = src
            existing.vehicle_type = event.vehicle_type
            existing.vehicle_color = event.vehicle_color
            existing.plate_number_normalized = event.plate_number_normalized
            existing.camera_code = event.camera_code
            existing.timestamp = event.timestamp
            row = existing
        else:
            row = VehicleEmbedding(
                vehicle_event_id=event.id,
                plate_number_normalized=event.plate_number_normalized,
                camera_id=event.camera_id,
                camera_code=event.camera_code,
                track_id=event.track_id,
                timestamp=event.timestamp,
                vehicle_type=event.vehicle_type,
                vehicle_color=event.vehicle_color,
                embedding=vec,
                dim=len(vec),
                model_name=model_name,
                source=src,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def backfill(self, limit: Optional[int] = None) -> dict:
        """Index events that have no embedding yet (bounded). Returns
        {scanned, indexed}."""
        cap = min(limit or settings.REID_BACKFILL_BATCH, settings.REID_BACKFILL_BATCH)
        indexed_ids = select(VehicleEmbedding.vehicle_event_id)
        rows = self.db.execute(
            select(VehicleEvent)
            .where(VehicleEvent.id.not_in(indexed_ids))
            .order_by(VehicleEvent.timestamp.desc())
            .limit(cap)
        ).scalars().all()
        n = 0
        for ev in rows:
            try:
                self.index_event(ev)
                n += 1
            except Exception:  # noqa: BLE001 -- one bad row must not abort the batch
                logger.exception("re-id backfill failed for event %s", ev.id)
                self.db.rollback()
        return {"scanned": len(rows), "indexed": n}

    # ---- comparison / search ------------------------------------------- #
    def _get_row(self, event_id: str) -> Optional[VehicleEmbedding]:
        return self.db.execute(
            select(VehicleEmbedding).where(
                VehicleEmbedding.vehicle_event_id == event_id
            )
        ).scalar_one_or_none()

    def _get_event(self, event_id: str) -> Optional[VehicleEvent]:
        return self.db.get(VehicleEvent, event_id)

    def _ensure_row(self, event_id: str) -> Optional[VehicleEmbedding]:
        row = self._get_row(event_id)
        if row:
            return row
        ev = self._get_event(event_id)
        if not ev:
            return None
        return self.index_event(ev)

    def compare(self, event_id_a: str, event_id_b: str) -> Optional[dict]:
        a = self._ensure_row(event_id_a)
        b = self._ensure_row(event_id_b)
        if not a or not b:
            return None
        score = cosine_similarity(a.embedding, b.embedding)
        band, conf = similarity_band(score)
        same_plate = (
            a.plate_number_normalized == b.plate_number_normalized
            and a.plate_number_normalized not in ("", "UNKNOWN")
        )
        return {
            "event_id_a": event_id_a,
            "event_id_b": event_id_b,
            "similarity": round(score, 4),
            "similarity_pct": round(score * 100, 1),
            "band": band,
            "confidence_level": conf.value,
            "same_plate": same_plate,
            "model_name": a.model_name,
            "note": (
                "Exact plate match -- deterministically the same vehicle."
                if same_plate
                else "VISUAL MATCH only. Visual similarity is not identity."
            ),
        }

    def rank_candidates(
        self, query: list[float], rows: Iterable[VehicleEmbedding]
    ) -> list[tuple[VehicleEmbedding, float]]:
        scored = [(r, cosine_similarity(query, r.embedding)) for r in rows]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def find_similar(
        self,
        *,
        event_id: Optional[str] = None,
        embedding: Optional[list[float]] = None,
        limit: int = 20,
        time_window_hours: Optional[int] = None,
        exclude_same_plate: bool = False,
        exclude_same_camera: bool = False,
        min_similarity: Optional[float] = None,
        auto_index: bool = True,
    ) -> dict:
        """Bounded appearance search. Loads at most REID_MAX_CANDIDATES rows
        (time-ordered, optionally windowed), ranks by cosine similarity in
        process, returns the top `limit`.

        `auto_index` (default True) first runs a bounded, idempotent backfill
        so a search still works on a DB whose events predate embedding
        indexing (migration day, or a deployment with REID_AUTO_INDEX off)."""
        if auto_index:
            try:
                self.backfill(settings.REID_MAX_CANDIDATES)
            except Exception:  # noqa: BLE001
                logger.exception("re-id search auto-backfill failed (continuing)")
                self.db.rollback()

        query_vec = embedding
        origin: Optional[VehicleEmbedding] = None
        origin_event: Optional[VehicleEvent] = None
        if query_vec is None:
            if not event_id:
                return {"query": None, "candidates": [], "note": "no query event or embedding"}
            origin = self._ensure_row(event_id)
            if not origin:
                return {"query": None, "candidates": [], "note": "query event not found"}
            origin_event = self._get_event(event_id)
            query_vec = origin.embedding

        conds = [VehicleEmbedding.vehicle_event_id != (event_id or "")]
        if time_window_hours and origin is not None:
            from datetime import timedelta

            lo = origin.timestamp - timedelta(hours=time_window_hours)
            hi = origin.timestamp + timedelta(hours=time_window_hours)
            conds.append(VehicleEmbedding.timestamp >= lo)
            conds.append(VehicleEmbedding.timestamp <= hi)
        if exclude_same_plate and origin is not None and origin.plate_number_normalized not in ("", "UNKNOWN"):
            conds.append(
                VehicleEmbedding.plate_number_normalized != origin.plate_number_normalized
            )
        if exclude_same_camera and origin is not None:
            conds.append(VehicleEmbedding.camera_id != origin.camera_id)

        rows = self.db.execute(
            select(VehicleEmbedding)
            .where(*conds)
            .order_by(VehicleEmbedding.timestamp.desc())
            .limit(settings.REID_MAX_CANDIDATES)
        ).scalars().all()

        ranked = self.rank_candidates(query_vec, rows)
        floor = settings.REID_SIMILARITY_WEAK if min_similarity is None else min_similarity

        # camera-code lookup for display (bounded -- only the top slice)
        top = [(r, s) for r, s in ranked if s >= floor][:limit]
        cam_ids = {r.camera_id for r, _ in top}
        cam_names = dict(
            self.db.execute(
                select(Camera.id, Camera.name).where(Camera.id.in_(cam_ids or ["-"]))
            ).all()
        )

        origin_plate = origin.plate_number_normalized if origin else None
        candidates = []
        for r, score in top:
            band, conf = similarity_band(score)
            same_plate = bool(
                origin_plate
                and origin_plate not in ("", "UNKNOWN")
                and r.plate_number_normalized == origin_plate
            )
            candidates.append({
                "event_id": r.vehicle_event_id,
                "plate_number_normalized": r.plate_number_normalized,
                "camera_id": r.camera_id,
                "camera_code": r.camera_code,
                "camera_name": cam_names.get(r.camera_id),
                "track_id": r.track_id,
                "timestamp": r.timestamp,
                "vehicle_type": r.vehicle_type,
                "vehicle_color": r.vehicle_color,
                "similarity": round(score, 4),
                "similarity_pct": round(score * 100, 1),
                "band": band,
                "confidence_level": conf.value,
                "same_plate": same_plate,
                "verdict": "PLATE MATCH" if same_plate else "VISUAL MATCH",
            })

        return {
            "query_event_id": event_id,
            "query_plate": origin_plate,
            "query_vehicle_type": origin_event.vehicle_type if origin_event else None,
            "query_vehicle_color": origin_event.vehicle_color if origin_event else None,
            "model_name": origin.model_name if origin else self.backend.name,
            "scanned": len(rows),
            "returned": len(candidates),
            "candidates": candidates,
            "disclaimer": (
                "VISUAL MATCH results rank appearance similarity only. Visual "
                "similarity is not identity -- treat as investigative leads, "
                "not confirmation, unless a plate match is also shown."
            ),
        }
