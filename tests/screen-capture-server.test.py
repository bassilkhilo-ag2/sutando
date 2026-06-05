"""Unit tests for src/screen-capture-server.py.

Tests the pure logic (display sanitization, format validation, notify debounce,
env flags) and the HTTP handler endpoints via a real server on an ephemeral port.

Run: `python3 tests/screen-capture-server.test.py`
"""
import http.client
import http.server
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "screen-capture-server.py"

sys.path.insert(0, str(ROOT / "src"))


def _load():
    spec = importlib.util.spec_from_file_location("screen_capture_server", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Display-number parsing (inline logic from do_GET line 108)
# ---------------------------------------------------------------------------

def _parse_display(raw):
    """Replicate the display-number coercion from do_GET."""
    if raw and raw.isdigit() and 1 <= int(raw) <= 9:
        return int(raw)
    return None


class TestDisplayParsing(unittest.TestCase):
    def test_valid_single_digit(self):
        self.assertEqual(_parse_display("1"), 1)
        self.assertEqual(_parse_display("5"), 5)
        self.assertEqual(_parse_display("9"), 9)

    def test_zero_returns_none(self):
        self.assertIsNone(_parse_display("0"))

    def test_ten_returns_none(self):
        self.assertIsNone(_parse_display("10"))

    def test_none_raw_returns_none(self):
        self.assertIsNone(_parse_display(None))

    def test_alpha_returns_none(self):
        self.assertIsNone(_parse_display("abc"))

    def test_float_string_returns_none(self):
        # "2.5".isdigit() is False
        self.assertIsNone(_parse_display("2.5"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_display(""))


# ---------------------------------------------------------------------------
# Format validation (inline logic from do_GET lines 112-115)
# ---------------------------------------------------------------------------

def _parse_format(fmt):
    """Replicate format validation + ext/type_flag resolution."""
    if fmt not in ("png", "jpg", "jpeg"):
        fmt = "png"
    ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
    type_flag = "jpg" if ext == "jpg" else "png"
    return ext, type_flag


class TestFormatValidation(unittest.TestCase):
    def test_png(self):
        ext, flag = _parse_format("png")
        self.assertEqual(ext, "png")
        self.assertEqual(flag, "png")

    def test_jpg(self):
        ext, flag = _parse_format("jpg")
        self.assertEqual(ext, "jpg")
        self.assertEqual(flag, "jpg")

    def test_jpeg_maps_to_jpg(self):
        ext, flag = _parse_format("jpeg")
        self.assertEqual(ext, "jpg")
        self.assertEqual(flag, "jpg")

    def test_gif_falls_back_to_png(self):
        ext, flag = _parse_format("gif")
        self.assertEqual(ext, "png")
        self.assertEqual(flag, "png")

    def test_empty_falls_back_to_png(self):
        ext, flag = _parse_format("")
        self.assertEqual(ext, "png")


# ---------------------------------------------------------------------------
# NOTIFY_ENABLED flag
# ---------------------------------------------------------------------------

class TestNotifyEnabled(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SUTANDO_CAPTURE_NOTIFY", None)

    def test_enabled_by_default(self):
        mod = _load()
        self.assertTrue(mod.NOTIFY_ENABLED)

    def test_disabled_when_env_is_zero(self):
        os.environ["SUTANDO_CAPTURE_NOTIFY"] = "0"
        mod = _load()
        self.assertFalse(mod.NOTIFY_ENABLED)

    def test_enabled_when_env_is_one(self):
        os.environ["SUTANDO_CAPTURE_NOTIFY"] = "1"
        mod = _load()
        self.assertTrue(mod.NOTIFY_ENABLED)


# ---------------------------------------------------------------------------
# Notify debounce
# ---------------------------------------------------------------------------

class TestNotifyDebounce(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.mod._last_notify_ts = 0.0

    def test_first_call_fires(self):
        fired = []
        with patch.object(self.mod.threading, "Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            self.mod._notify_capture()
        # _last_notify_ts should be updated
        self.assertGreater(self.mod._last_notify_ts, 0)

    def test_second_call_within_debounce_skipped(self):
        self.mod._last_notify_ts = time.time()  # pretend it just fired
        with patch.object(self.mod.threading, "Thread") as mock_thread:
            self.mod._notify_capture()
            mock_thread.assert_not_called()

    def test_call_after_debounce_fires(self):
        self.mod._last_notify_ts = time.time() - 10  # 10s ago — past debounce
        with patch.object(self.mod.threading, "Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            self.mod._notify_capture()
            mock_thread.assert_called_once()

    def test_disabled_notify_skips_thread(self):
        self.mod.NOTIFY_ENABLED = False
        with patch.object(self.mod.threading, "Thread") as mock_thread:
            self.mod._notify_capture()
            mock_thread.assert_not_called()
        self.mod.NOTIFY_ENABLED = True


# ---------------------------------------------------------------------------
# HTTP handler tests — real server on an ephemeral port
# ---------------------------------------------------------------------------

class TestHandlerHTTP(unittest.TestCase):
    """Integration-style tests against a live Handler on a random port.

    subprocess.run is mocked so screencapture is never actually called.
    When the mock is invoked, we create a 1-byte stub at the expected path so
    the capture_all path's os.path.exists / os.path.getsize checks pass.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load()
        # Suppress notifications and seeing signals during tests
        cls.mod.NOTIFY_ENABLED = False
        cls.mod._signal_seeing = lambda: None

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), cls.mod.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read()

    def _fake_screencapture(self, cmd, **kwargs):
        """Mock subprocess.run: create a 1-byte stub at the output path."""
        path = cmd[-1]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_bytes(b"x")
        m = MagicMock()
        m.returncode = 0
        return m

    def test_ping(self):
        status, body = self._get("/ping")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"pong": True})

    def test_unknown_path_404(self):
        status, _ = self._get("/unknown")
        self.assertEqual(status, 404)

    def test_capture_returns_200_with_path(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture):
            status, body = self._get("/capture")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")
        self.assertIn("path", data)

    def test_capture_png_default(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture):
            status, body = self._get("/capture?format=png")
        data = json.loads(body)
        self.assertTrue(data["path"].endswith(".png"))

    def test_capture_jpg_format(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture):
            status, body = self._get("/capture?format=jpg")
        data = json.loads(body)
        self.assertTrue(data["path"].endswith(".jpg"))

    def test_capture_invalid_format_defaults_to_png(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture):
            status, body = self._get("/capture?format=gif")
        data = json.loads(body)
        self.assertTrue(data["path"].endswith(".png"))

    def test_capture_with_valid_display(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture) as mock_run:
            status, body = self._get("/capture?display=2")
        self.assertEqual(status, 200)
        # -D2 should appear in the screencapture command
        args = mock_run.call_args[0][0]
        self.assertIn("-D2", args)

    def test_capture_with_invalid_display_omits_flag(self):
        with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture) as mock_run:
            status, body = self._get("/capture?display=99")
        self.assertEqual(status, 200)
        args = mock_run.call_args[0][0]
        self.assertFalse(any(a.startswith("-D") for a in args))

    def test_capture_silent_suppresses_seeing(self):
        seen_calls = []
        original = self.mod._signal_seeing
        self.mod._signal_seeing = lambda: seen_calls.append(1)
        try:
            with patch.object(self.mod.subprocess, "run", side_effect=self._fake_screencapture):
                self._get("/capture?silent=true")
        finally:
            self.mod._signal_seeing = original
        self.assertEqual(seen_calls, [])

    def test_capture_subprocess_failure_returns_500(self):
        def fail_run(cmd, **kwargs):
            raise RuntimeError("screencapture not found")
        with patch.object(self.mod.subprocess, "run", side_effect=fail_run):
            status, body = self._get("/capture")
        self.assertEqual(status, 500)
        data = json.loads(body)
        self.assertEqual(data["status"], "error")


if __name__ == "__main__":
    unittest.main()
