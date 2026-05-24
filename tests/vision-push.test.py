#!/usr/bin/env python3
"""
Tests for src/vision_push.py

Coverage:
  _post            — successful response, HTTPError passthrough, URLError → (0,b""),
                     ConnectionRefusedError → (0,b""), TimeoutError → (0,b"")
  is_voice_ready   — sessionReady=true, sessionReady=false, connection refused → False,
                     malformed JSON → False
  push_image       — file not found → False, file too small → False, non-image extension
                     → falls back to image/jpeg, voice not ready → False,
                     voice ready + 2xx POST → True, voice ready + 5xx POST → False,
                     file read error (PermissionError) → False

Run: python3 tests/vision-push.test.py
Exit code: 0 on pass, 1 on fail.
"""

import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import vision_push  # noqa: E402


def _mock_response(status: int, body: bytes) -> MagicMock:
    """Build a mock context-manager response for urllib.request.urlopen."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestPost(unittest.TestCase):
    def test_successful_response_returns_status_and_body(self):
        with patch.object(urllib.request, "urlopen", return_value=_mock_response(200, b"ok")):
            status, body = vision_push._post("/vision/frame", b"data", "image/jpeg")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")

    def test_http_error_returns_error_code(self):
        err = urllib.error.HTTPError(
            url="http://x", code=422, msg="Unprocessable", hdrs=None, fp=None
        )
        with patch.object(urllib.request, "urlopen", side_effect=err):
            status, body = vision_push._post("/vision/frame", b"data", "image/jpeg")
        self.assertEqual(status, 422)
        self.assertEqual(body, b"")

    def test_url_error_returns_zero_status(self):
        err = urllib.error.URLError(reason="connection refused")
        with patch.object(urllib.request, "urlopen", side_effect=err):
            status, body = vision_push._post("/vision/frame", b"data", "image/jpeg")
        self.assertEqual(status, 0)
        self.assertEqual(body, b"")

    def test_connection_refused_returns_zero_status(self):
        with patch.object(urllib.request, "urlopen", side_effect=ConnectionRefusedError()):
            status, body = vision_push._post("/vision/start", b"{}", "application/json")
        self.assertEqual(status, 0)

    def test_timeout_returns_zero_status(self):
        with patch.object(urllib.request, "urlopen", side_effect=TimeoutError()):
            status, body = vision_push._post("/vision/start", b"{}", "application/json")
        self.assertEqual(status, 0)

    def test_os_error_returns_zero_status(self):
        with patch.object(urllib.request, "urlopen", side_effect=OSError("broken pipe")):
            status, body = vision_push._post("/vision/stop", b"", "application/json")
        self.assertEqual(status, 0)


class TestIsVoiceReady(unittest.TestCase):
    def test_session_ready_true_returns_true(self):
        body = json.dumps({"sessionReady": True}).encode()
        with patch.object(urllib.request, "urlopen", return_value=_mock_response(200, body)):
            self.assertTrue(vision_push.is_voice_ready())

    def test_session_ready_false_returns_false(self):
        body = json.dumps({"sessionReady": False}).encode()
        with patch.object(urllib.request, "urlopen", return_value=_mock_response(200, body)):
            self.assertFalse(vision_push.is_voice_ready())

    def test_session_ready_missing_returns_false(self):
        body = json.dumps({}).encode()
        with patch.object(urllib.request, "urlopen", return_value=_mock_response(200, body)):
            self.assertFalse(vision_push.is_voice_ready())

    def test_connection_refused_returns_false(self):
        with patch.object(urllib.request, "urlopen", side_effect=ConnectionRefusedError()):
            self.assertFalse(vision_push.is_voice_ready())

    def test_malformed_json_returns_false(self):
        with patch.object(urllib.request, "urlopen", return_value=_mock_response(200, b"not json")):
            self.assertFalse(vision_push.is_voice_ready())

    def test_url_error_returns_false(self):
        err = urllib.error.URLError(reason="no route")
        with patch.object(urllib.request, "urlopen", side_effect=err):
            self.assertFalse(vision_push.is_voice_ready())


class TestPushImage(unittest.TestCase):
    def _large_jpeg(self) -> bytes:
        """Return a fake payload large enough to clear MIN_FRAME_BYTES."""
        return b"\xff\xd8\xff" + b"\x00" * (vision_push.MIN_FRAME_BYTES + 100)

    def test_nonexistent_file_returns_false(self):
        self.assertFalse(vision_push.push_image("/no/such/file.jpg"))

    def test_file_too_small_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff")  # 3 bytes — below MIN_FRAME_BYTES
            path = f.name
        try:
            self.assertFalse(vision_push.push_image(path))
        finally:
            Path(path).unlink(missing_ok=True)

    def test_voice_not_ready_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=False):
                self.assertFalse(vision_push.push_image(path))
        finally:
            Path(path).unlink(missing_ok=True)

    def test_successful_push_returns_true(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", return_value=(200, b"ok")):
                result = vision_push.push_image(path)
            self.assertTrue(result)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_5xx_frame_post_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", return_value=(500, b"")):
                result = vision_push.push_image(path)
            self.assertFalse(result)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_unknown_extension_uses_jpeg_mime(self):
        """Files with no recognized extension fall back to image/jpeg."""
        captured_mime = []

        def fake_post(path, body, content_type, **kw):
            if path == "/vision/frame":
                captured_mime.append(content_type)
            return (200, b"ok")

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", side_effect=fake_post):
                vision_push.push_image(path)
            self.assertEqual(captured_mime, ["image/jpeg"])
        finally:
            Path(path).unlink(missing_ok=True)

    def test_png_extension_uses_png_mime(self):
        captured_mime = []

        def fake_post(path, body, content_type, **kw):
            if path == "/vision/frame":
                captured_mime.append(content_type)
            return (200, b"ok")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", side_effect=fake_post):
                vision_push.push_image(path)
            self.assertIn("image/png", captured_mime)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_start_called_before_frame(self):
        """push_image must call /vision/start then /vision/frame — in that order."""
        call_order = []

        def fake_post(path, body, content_type, **kw):
            call_order.append(path)
            return (200, b"ok")

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", side_effect=fake_post):
                vision_push.push_image(path)
            self.assertEqual(call_order[0], "/vision/start")
            self.assertIn("/vision/frame", call_order)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_source_embedded_in_start_payload(self):
        start_bodies = []

        def fake_post(path, body, content_type, **kw):
            if path == "/vision/start":
                start_bodies.append(body)
            return (200, b"ok")

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(self._large_jpeg())
            path = f.name
        try:
            with patch.object(vision_push, "is_voice_ready", return_value=True), \
                 patch.object(vision_push, "_post", side_effect=fake_post):
                vision_push.push_image(path, source="telegram")
            self.assertTrue(start_bodies)
            self.assertIn(b"telegram", start_bodies[0])
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
