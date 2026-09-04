"""
PHASE 6 — ingest API-key authentication on POST /api/v1/events/ai-detection.

DB-gated (needs SENTINEL_TEST_DATABASE_URL). Covers valid key, invalid key,
missing credentials, and the operator-JWT alternative.
"""
import os
import unittest

DB_URL = os.getenv("SENTINEL_TEST_DATABASE_URL")
if DB_URL:
    os.environ["DATABASE_URL"] = DB_URL
    os.environ["INGEST_API_KEY"] = "unit-test-key"

_EVENT = {
    "camera_id": "cam-auth-test",
    "timestamp": "2026-09-01T10:00:00Z",
    "track_id": 1,
    "vehicle": {"type": "car", "confidence": 0.9, "bbox": [1, 2, 3, 4], "track_id": 1},
    "license_plate": {"plate_number": "GJ01ZZ0001", "text": "GJ01ZZ0001", "confidence": 0.9},
    "evidence": {"frame_snapshot_path": "/tmp/none.jpg"},
}


@unittest.skipUnless(DB_URL, "set SENTINEL_TEST_DATABASE_URL")
class TestIngestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        from fastapi.testclient import TestClient
        import app.config as cfg
        importlib.reload(cfg)
        import app.database as dbm
        importlib.reload(dbm)
        from app.main import app
        from app.database import SessionLocal
        from app.core.security import hash_password
        from app.models.base import UserRole
        from app.models.user import User
        from sqlalchemy import text

        cls.client = TestClient(app)
        with SessionLocal() as s:
            s.execute(text("DELETE FROM users WHERE username='auth-op'"))
            s.add(User(username="auth-op", email="op@x.com",
                       hashed_password=hash_password("pw12345678"),
                       role=UserRole.OPERATOR, is_active=True))
            s.commit()
        cls.jwt = cls.client.post("/api/v1/auth/login",
                                  json={"username": "auth-op", "password": "pw12345678"}
                                  ).json()["access_token"]

    def _post(self, headers):
        return self.client.post("/api/v1/events/ai-detection", json=_EVENT, headers=headers)

    def test_valid_key_accepted(self):
        r = self._post({"X-Ingest-Key": "unit-test-key"})
        self.assertEqual(r.status_code, 201, r.text)

    def test_invalid_key_rejected(self):
        r = self._post({"X-Ingest-Key": "wrong-key"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("unit-test-key", r.text)

    def test_missing_credentials_rejected(self):
        r = self._post({})
        self.assertEqual(r.status_code, 401)

    def test_operator_jwt_accepted(self):
        r = self._post({"Authorization": f"Bearer {self.jwt}"})
        self.assertEqual(r.status_code, 201, r.text)

    def test_bad_jwt_rejected(self):
        r = self._post({"Authorization": "Bearer not.a.jwt"})
        self.assertEqual(r.status_code, 401)


class TestPasswordHashing(unittest.TestCase):
    """bcrypt-direct hashing (passlib removed) — always runs."""

    def test_hash_and_verify(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
        from app.core.security import hash_password, verify_password

        h = hash_password("A very Str0ng p@ssphrase !!")
        self.assertTrue(h.startswith("$2"))
        self.assertTrue(verify_password("A very Str0ng p@ssphrase !!", h))
        self.assertFalse(verify_password("wrong", h))
        self.assertFalse(verify_password("x", ""))
        # >72 byte passwords must not raise
        self.assertTrue(verify_password("x" * 200, hash_password("x" * 200)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
