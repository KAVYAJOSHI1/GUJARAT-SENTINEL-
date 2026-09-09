"""
Phase 19 Part H -- backend-side failure resilience.

Principle under test: infrastructure the backend depends on (the
database, object storage) going away must degrade the ONE request that
needed it, cleanly and honestly -- never crash the process, never leak a
raw traceback, never silently pretend something worked.
"""
import os
import shutil
import tempfile
from unittest import mock

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app as fastapi_app
from conftest import bearer


class _RaisingSession:
    """Stands in for a real DB session whose connection has dropped."""

    def __init__(self, exc):
        self._exc = exc

    def execute(self, *a, **kw):
        raise self._exc

    def get(self, *a, **kw):
        raise self._exc

    def commit(self):
        raise self._exc

    def close(self):
        pass


def test_database_unavailable_returns_clean_500_not_a_crash(client, officer_user):
    _, tok = officer_user

    def _raise_db():
        yield _RaisingSession(OperationalError("SELECT 1", {}, Exception("connection refused")))

    fastapi_app.dependency_overrides[get_db] = _raise_db
    try:
        r = client.get("/api/v1/system/metrics/summary", headers=bearer(tok))
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 500
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    # never a raw traceback / stack frame leaking into the response
    assert "Traceback" not in r.text and "File \"" not in r.text


def test_unexpected_exception_still_returns_the_standard_envelope(officer_user):
    """A bare Exception (not OperationalError, not a SentinelException) is
    handled by Starlette's ServerErrorMiddleware path -- which re-raises
    to the ASGI transport for real deployments' error logging AFTER
    already building the JSON response below. TestClient's default
    raise_server_exceptions=True surfaces that re-raise to the test
    itself (a TestClient-only quirk, not something a real client ever
    sees) unless disabled here, which is exactly what this test needs to
    inspect the response our handler actually sent."""
    from starlette.testclient import TestClient

    _, tok = officer_user

    def _raise_generic():
        yield _RaisingSession(RuntimeError("something genuinely unexpected"))

    fastapi_app.dependency_overrides[get_db] = _raise_generic
    try:
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            r = c.get("/api/v1/system/metrics/summary", headers=bearer(tok))
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 500
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "RuntimeError" not in r.text  # never leak the exception's own message/type


class TestObjectStorageFallback:
    """MinioService: 'falls back to a local disk folder transparently if
    MinIO is unreachable' (its own module docstring) -- proven here, not
    just asserted."""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp(prefix="sentinel-minio-fallback-")

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_unreachable_minio_endpoint_falls_back_to_local_disk(self):
        from app.config import settings
        from app.services.minio_service import MinioService

        with mock.patch.object(settings, "MINIO_ENDPOINT", "127.0.0.1:1"), \
             mock.patch.object(settings, "LOCAL_EVIDENCE_FALLBACK_DIR", self._tmp):
            svc = MinioService()
            assert svc._client is None, "should have given up on MinIO, not hung retrying"

            ref = svc.upload_snapshot(
                camera_id="cam-fail-1", plate="GJ01AB1234",
                snapshot_base64="/9j/4AAQSkZJRgABAQEAAAAAAAD//gA7Q1JFQVRPUjogZ2QtanBlZyB2MS4wICh1c2luZyBJSkcgSlBFRyB2NjIpLCBxdWFsaXR5ID0gOTAK/9sAQwAI",
                content_type="image/jpeg",
            )
            assert ref is not None
            written = os.listdir(self._tmp)
            assert len(written) >= 1, "fallback wrote nothing to local disk"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
