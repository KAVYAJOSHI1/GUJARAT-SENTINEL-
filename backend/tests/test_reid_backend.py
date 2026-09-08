"""
Phase 15E -- Re-ID embedding backend selection + status + torch fallback.
"""
import math

import pytest

from app.services.ai import reid as reid_mod
from app.services.ai.reid import (
    AttributeEmbeddingBackend,
    get_embedding_backend,
    reid_backend_status,
)
from conftest import bearer


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def test_default_backend_is_attribute():
    be = get_embedding_backend("attribute")
    assert isinstance(be, AttributeEmbeddingBackend)
    assert be.name == "attr-baseline-v1"


def test_status_shape():
    s = reid_backend_status()
    for k in ("requested_backend", "active_backend", "model", "device", "loaded",
              "embedding_dimension", "candidate_limit", "similarity_thresholds"):
        assert k in s
    assert s["active_backend"] in ("attribute", "torch")
    assert s["loaded"] is True
    assert "not identity" in s["note"]


def test_unknown_backend_name_falls_back_to_attribute():
    be = get_embedding_backend("does-not-exist")
    assert isinstance(be, AttributeEmbeddingBackend)


def test_torch_fallback_when_import_fails(monkeypatch):
    # simulate torch not importable -> get_embedding_backend must not raise
    reid_mod._BACKEND_CACHE.pop("torch", None)

    class _Boom(reid_mod.TorchEmbeddingBackend):
        def __init__(self, *a, **k):
            raise RuntimeError("no torch here")

    monkeypatch.setattr(reid_mod, "TorchEmbeddingBackend", _Boom)
    be = get_embedding_backend("torch")
    assert isinstance(be, AttributeEmbeddingBackend)
    assert reid_mod._BACKEND_STATUS["fell_back"] is True
    reid_mod._BACKEND_CACHE.pop("torch", None)


def test_status_endpoint(client, officer_user):
    _, tok = officer_user
    r = client.get("/api/v1/ai/reid/status", headers=bearer(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["embedding_dimension"] > 0
    assert body["candidate_limit"] >= 1


def test_status_endpoint_requires_auth(client):
    assert client.get("/api/v1/ai/reid/status").status_code == 401


@pytest.mark.slow
def test_torch_backend_loads_when_available():
    """torch IS in the dev venv -- verify the CNN backbone produces a
    normalised vector. Skipped implicitly in envs without torch."""
    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    pytest.importorskip("PIL")
    import numpy as np

    reid_mod._BACKEND_CACHE.pop("torch", None)
    be = reid_mod.TorchEmbeddingBackend("mobilenet_v3_small")
    assert be.dim == 576
    crop = (np.random.default_rng(1).integers(0, 255, (120, 200, 3))).astype("uint8")
    vec = be.extract({"crop_array": crop})
    assert len(vec) == 576
    assert abs(_norm(vec) - 1.0) < 1e-4
    reid_mod._BACKEND_CACHE.pop("torch", None)
