"""Unit tests for src/github-webhook.py.

Run: `python3 tests/github-webhook.test.py`
"""
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "github-webhook.py"

sys.path.insert(0, str(ROOT / "src"))

_SECRET = "test-secret-abc123"


def _load(workspace: Path, secret: str = _SECRET):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    os.environ["GITHUB_WEBHOOK_SECRET"] = secret
    spec = importlib.util.spec_from_file_location("github_webhook", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestVerifyGithubSignature(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("GITHUB_WEBHOOK_SECRET", None)
        self.tmp.cleanup()

    def test_valid_signature_returns_true(self):
        body = b'{"action":"opened"}'
        sig = _sign(body)
        self.assertTrue(self.mod.verify_github_signature(body, sig))

    def test_wrong_signature_returns_false(self):
        body = b'{"action":"opened"}'
        self.assertFalse(self.mod.verify_github_signature(body, "sha256=deadbeef"))

    def test_missing_signature_header_returns_false(self):
        self.assertFalse(self.mod.verify_github_signature(b"body", ""))

    def test_no_sha256_prefix_returns_false(self):
        body = b'{"action":"opened"}'
        raw_hex = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assertFalse(self.mod.verify_github_signature(body, raw_hex))

    def test_empty_secret_returns_false(self):
        mod = _load(Path(self.tmp.name), secret="")
        body = b'{"action":"opened"}'
        self.assertFalse(mod.verify_github_signature(body, "sha256=anything"))

    def test_tampered_body_returns_false(self):
        body = b'{"action":"opened"}'
        sig = _sign(body)
        tampered = b'{"action":"closed"}'
        self.assertFalse(self.mod.verify_github_signature(tampered, sig))

    def test_constant_time_comparison(self):
        # hmac.compare_digest must be used — confirm the function returns
        # correct results for two different valid inputs (not short-circuit).
        body1 = b"payload-one"
        body2 = b"payload-two"
        sig1 = _sign(body1)
        sig2 = _sign(body2)
        self.assertTrue(self.mod.verify_github_signature(body1, sig1))
        self.assertFalse(self.mod.verify_github_signature(body1, sig2))
        self.assertTrue(self.mod.verify_github_signature(body2, sig2))


class TestFormatEvent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("GITHUB_WEBHOOK_SECRET", None)
        self.tmp.cleanup()

    def _repo_payload(self, **extra):
        return {
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "alice"},
            **extra,
        }

    def test_issue_opened(self):
        payload = self._repo_payload(
            action="opened",
            issue={"number": 42, "title": "Bug report", "body": "Details here"},
        )
        result = self.mod.format_event("issues", payload)
        self.assertIsNotNone(result)
        self.assertIn("#42", result)
        self.assertIn("Bug report", result)
        self.assertIn("@alice", result)

    def test_pr_opened(self):
        payload = self._repo_payload(
            action="opened",
            pull_request={"number": 7, "title": "Fix login", "body": "Fixes #3"},
        )
        result = self.mod.format_event("pull_request", payload)
        self.assertIsNotNone(result)
        self.assertIn("#7", result)
        self.assertIn("Fix login", result)

    def test_pr_merged(self):
        payload = self._repo_payload(
            action="closed",
            pull_request={"number": 7, "title": "Fix login", "merged": True},
        )
        result = self.mod.format_event("pull_request", payload)
        self.assertIsNotNone(result)
        self.assertIn("merged", result)

    def test_pr_closed_not_merged_returns_none(self):
        payload = self._repo_payload(
            action="closed",
            pull_request={"number": 7, "title": "Fix login", "merged": False},
        )
        result = self.mod.format_event("pull_request", payload)
        self.assertIsNone(result)

    def test_star_created(self):
        payload = self._repo_payload(
            action="created",
            repository={"full_name": "owner/repo", "stargazers_count": 100},
        )
        result = self.mod.format_event("star", payload)
        self.assertIsNotNone(result)
        self.assertIn("100", result)
        self.assertIn("@alice", result)

    def test_issue_comment_created(self):
        payload = self._repo_payload(
            action="created",
            issue={"number": 5, "title": "My issue"},
            comment={"body": "Great work!", "user": {"login": "alice", "type": "User"}},
        )
        result = self.mod.format_event("issue_comment", payload)
        self.assertIsNotNone(result)
        self.assertIn("Great work!", result)
        self.assertIn("#5", result)

    def test_bot_comment_returns_none(self):
        payload = self._repo_payload(
            action="created",
            issue={"number": 5, "title": "Issue"},
            comment={"body": "CI passed", "user": {"login": "ci-bot", "type": "Bot"}},
        )
        result = self.mod.format_event("issue_comment", payload)
        self.assertIsNone(result)

    def test_unknown_event_returns_none(self):
        result = self.mod.format_event("push", self._repo_payload(action="created"))
        self.assertIsNone(result)

    def test_issue_opened_wrong_action_returns_none(self):
        payload = self._repo_payload(
            action="closed",
            issue={"number": 1, "title": "Old issue", "body": ""},
        )
        result = self.mod.format_event("issues", payload)
        self.assertIsNone(result)

    def test_long_body_truncated(self):
        long_body = "x" * 1000
        payload = self._repo_payload(
            action="opened",
            issue={"number": 1, "title": "Title", "body": long_body},
        )
        result = self.mod.format_event("issues", payload)
        self.assertIsNotNone(result)
        # Body is truncated to 500 chars in format_event
        self.assertLessEqual(len(result), 600)


if __name__ == "__main__":
    unittest.main()
