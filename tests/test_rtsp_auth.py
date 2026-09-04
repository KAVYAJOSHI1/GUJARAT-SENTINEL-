"""PHASE 1 — RTSP credential injection + redaction."""
import unittest

from ingestion.rtsp_auth import (
    apply_rtsp_credentials,
    has_inline_credentials,
    redact_rtsp_url,
)

URL = "rtsp://103.250.160.189:8554/stream/cam04"


class TestApplyCredentials(unittest.TestCase):
    def test_injects_userinfo(self):
        out = apply_rtsp_credentials(URL, "user", "pass")
        self.assertEqual(out, "rtsp://user:pass@103.250.160.189:8554/stream/cam04")

    def test_url_encodes_special_chars(self):
        out = apply_rtsp_credentials(URL, "u@ser", "p:a/s s")
        self.assertIn("u%40ser:p%3Aa%2Fs%20s@103.250.160.189:8554", out)
        self.assertNotIn(" ", out)

    def test_no_creds_returns_url_unchanged(self):
        self.assertEqual(apply_rtsp_credentials(URL, None, None), URL)
        self.assertEqual(apply_rtsp_credentials(URL, "user", None), URL)

    def test_env_fallback(self):
        import os

        os.environ["SENTINEL_RTSP_USERNAME"] = "envu"
        os.environ["SENTINEL_RTSP_PASSWORD"] = "envp"
        try:
            self.assertEqual(
                apply_rtsp_credentials(URL),
                "rtsp://envu:envp@103.250.160.189:8554/stream/cam04",
            )
        finally:
            del os.environ["SENTINEL_RTSP_USERNAME"]
            del os.environ["SENTINEL_RTSP_PASSWORD"]

    def test_existing_inline_creds_respected(self):
        inline = "rtsp://a:b@host:8554/s"
        self.assertTrue(has_inline_credentials(inline))
        self.assertEqual(apply_rtsp_credentials(inline, "user", "pass"), inline)

    def test_non_rtsp_untouched(self):
        for u in ("http://x/y", "/local/file.mp4", "0", None):
            self.assertEqual(apply_rtsp_credentials(u, "user", "pass"), u)


class TestRedaction(unittest.TestCase):
    def test_redacts_userinfo(self):
        self.assertEqual(
            redact_rtsp_url("rtsp://user:secretpw@host:8554/stream/cam04"),
            "rtsp://***:***@host:8554/stream/cam04",
        )

    def test_password_never_survives_redaction(self):
        authed = apply_rtsp_credentials(URL, "operator", "Sup3rSecret!")
        red = redact_rtsp_url(authed)
        self.assertNotIn("Sup3rSecret", red)
        self.assertNotIn("operator", red)
        self.assertIn("103.250.160.189:8554/stream/cam04", red)

    def test_plain_url_unchanged(self):
        self.assertEqual(redact_rtsp_url(URL), URL)

    def test_none_safe(self):
        self.assertIsNone(redact_rtsp_url(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
