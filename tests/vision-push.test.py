"""Unit tests for src/vision_push.py.

Run: `python3 tests/vision-push.test.py`
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "vision_push.py"

sys.path.insert(0, str(ROOT / "src"))


def _load():
    spec = importlib.util.spec_from_file_location("vision_push", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mock_resp(status: int, body: bytes):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestPost(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_success_returns_status_and_body(self):
        resp = _mock_resp(200, b"ok")
        with patch("urllib.request.urlopen", return_value=resp):
            status, body = self.mod._post("/vision/frame", b"data", "image/jpeg")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")

    def test_http_error_returns_error_code(self):
        err = urllib.error.HTTPError(
            url="http://x", code=500, msg="err", hdrs={}, fp=io.BytesIO(b"server error")
        )
        with patch("urllib.request.urlopen", side_effect=err):
            status, body = self.mod._post("/vision/frame", b"data", "image/jpeg")
        self.assertEqual(status, 500)
        self.assertIn(b"server error", body)

    def test_http_error_no_fp_returns_empty_body(self):
        err = urllib.error.HTTPError(
            url="http://x", code=404, msg="not found", hdrs={}, fp=None
        )
        with patch("urllib.request.urlopen", side_effect=err):
            status, body = self.mod._post("/vision/frame", b"x", "image/jpeg")
        self.assertEqual(status, 404)
        self.assertEqual(body, b"")

    def test_url_error_returns_zero(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            status, body = self.mod._post("/path", b"x", "text/plain")
        self.assertEqual(status, 0)
        self.assertEqual(body, b"")

    def test_connection_refused_returns_zero(self):
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            status, body = self.mod._post("/path", b"x", "text/plain")
        self.assertEqual(status, 0)

    def test_timeout_returns_zero(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            status, body = self.mod._post("/path", b"x", "text/plain")
        self.assertEqual(status, 0)

    def test_os_error_returns_zero(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            status, body = self.mod._post("/path", b"x", "text/plain")
        self.assertEqual(status, 0)


class TestIsVoiceReady(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def _urlopen_returning(self, payload: dict):
        body = json.dumps(payload).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_returns_true_when_session_ready(self):
        with patch("urllib.request.urlopen", return_value=self._urlopen_returning({"sessionReady": True})):
            self.assertTrue(self.mod.is_voice_ready())

    def test_returns_false_when_not_ready(self):
        with patch("urllib.request.urlopen", return_value=self._urlopen_returning({"sessionReady": False})):
            self.assertFalse(self.mod.is_voice_ready())

    def test_returns_false_when_field_missing(self):
        with patch("urllib.request.urlopen", return_value=self._urlopen_returning({})):
            self.assertFalse(self.mod.is_voice_ready())

    def test_returns_false_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertFalse(self.mod.is_voice_ready())

    def test_returns_false_on_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            self.assertFalse(self.mod.is_voice_ready())


class TestPushImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load()

    def tearDown(self):
        self.tmp.cleanup()

    def _jpeg(self, name: str, size: int = 3000) -> str:
        """Write a fake JPEG of a given byte size."""
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(b"\xff\xd8" + b"x" * (size - 2))
        return p

    def _png(self, name: str, size: int = 3000) -> str:
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as f:
            f.write(b"\x89PNG" + b"x" * (size - 4))
        return p

    def test_missing_file_returns_false(self):
        self.assertFalse(self.mod.push_image("/tmp/no-such-file-xyz.jpg"))

    def test_too_small_file_returns_false(self):
        p = self._jpeg("tiny.jpg", size=100)
        self.assertFalse(self.mod.push_image(p))

    def test_voice_not_ready_returns_false(self):
        p = self._jpeg("real.jpg")
        with patch.object(self.mod, "is_voice_ready", return_value=False):
            self.assertFalse(self.mod.push_image(p))

    def test_successful_jpeg_push_returns_true(self):
        p = self._jpeg("frame.jpg")
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(200, b"ok")) as mock_post:
                result = self.mod.push_image(p, source="test")
        self.assertTrue(result)
        # Should have called /vision/start and /vision/frame
        calls = [c[0][0] for c in mock_post.call_args_list]
        self.assertIn("/vision/start", calls)
        self.assertIn("/vision/frame", calls)

    def test_successful_png_push_returns_true(self):
        p = self._png("frame.png")
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(200, b"ok")):
                result = self.mod.push_image(p)
        self.assertTrue(result)

    def test_failed_frame_post_returns_false(self):
        p = self._jpeg("frame.jpg")
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(500, b"error")):
                self.assertFalse(self.mod.push_image(p))

    def test_unknown_extension_uses_jpeg_mime(self):
        p = os.path.join(self.tmp.name, "frame.bin")
        with open(p, "wb") as f:
            f.write(b"x" * 3000)
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(200, b"ok")) as mock_post:
                self.mod.push_image(p)
        # The frame post content-type should fall back to image/jpeg
        frame_calls = [c for c in mock_post.call_args_list if c[0][0] == "/vision/frame"]
        self.assertEqual(len(frame_calls), 1)
        self.assertEqual(frame_calls[0][0][2], "image/jpeg")

    def test_source_embedded_in_start_body(self):
        p = self._jpeg("frame.jpg")
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(200, b"ok")) as mock_post:
                self.mod.push_image(p, source="telegram")
        start_calls = [c for c in mock_post.call_args_list if c[0][0] == "/vision/start"]
        self.assertEqual(len(start_calls), 1)
        self.assertIn(b"telegram", start_calls[0][0][1])

    def test_file_read_oserror_returns_false(self):
        p = self._jpeg("unreadable.jpg")
        with patch("builtins.open", side_effect=OSError("permission denied")):
            self.assertFalse(self.mod.push_image(p))

    def test_min_frame_bytes_constant(self):
        self.assertEqual(self.mod.MIN_FRAME_BYTES, 2048)

    def test_2xx_statuses_succeed(self):
        p = self._jpeg("frame.jpg")
        for code in (200, 201, 204):
            with patch.object(self.mod, "is_voice_ready", return_value=True):
                with patch.object(self.mod, "_post", return_value=(code, b"")):
                    self.assertTrue(self.mod.push_image(p), f"status {code} should succeed")

    def test_3xx_returns_false(self):
        p = self._jpeg("frame.jpg")
        with patch.object(self.mod, "is_voice_ready", return_value=True):
            with patch.object(self.mod, "_post", return_value=(302, b"")):
                self.assertFalse(self.mod.push_image(p))


if __name__ == "__main__":
    unittest.main()
