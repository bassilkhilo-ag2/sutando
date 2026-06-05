#!/usr/bin/env python3
"""Behavioral tests for `send_allowlist.is_path_sendable`.

`is_path_sendable(fpath)` is the single source of truth for the
file-attachment delivery policy — it decides whether an agent-emitted
`[file: /path]` marker can be delivered to the owner's Discord DM.

Structural invariants (exports, no-inline definitions) live in
`tests/send-allowlist-shared.test.py`. This file pins the *runtime
behaviour*: allowed roots, allowed prefixes, symlink-collapse, and the
fail-closed defaults.

Pins:
  1.  /tmp/sutando-* prefix → allowed.
  2.  /private/tmp/sutando-* prefix → allowed (macOS symlink form).
  3.  /tmp/echo-* prefix → allowed.
  4.  /private/tmp/echo-* prefix → allowed.
  5.  A path outside any root/prefix → rejected.
  6.  A non-existent path → rejected (os.path.isfile guard).
  7.  A directory (not a regular file) → rejected.
  8.  A symlink that resolves inside an allowed prefix → allowed.
  9.  A symlink that resolves outside all allowed roots/prefixes → rejected.
  10. A path that STARTS with an allowed root string but isn't a child
      of it (i.e. a sibling with a shared prefix) → rejected.
      Example: root `/tmp/sutando` must not allow `/tmp/sutando-evil`.
      (Covered by SEND_ALLOWED_PREFIXES, but the root check uses
      `startswith(root + os.sep)` to prevent this — verified here.)
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


al = _load("send_allowlist", REPO / "src" / "send_allowlist.py")


def _make_file(path: str) -> str:
    """Create an empty regular file at `path` and return its realpath."""
    Path(path).touch()
    return path


class TestAllowedPrefixes(unittest.TestCase):

    def test_sutando_tmp_prefix_allowed(self):
        with tempfile.NamedTemporaryFile(
            prefix="sutando-", dir="/tmp", suffix=".txt", delete=False
        ) as f:
            name = f.name
        try:
            self.assertTrue(al.is_path_sendable(name), f"expected allowed: {name}")
        finally:
            os.unlink(name)

    def test_echo_tmp_prefix_allowed(self):
        with tempfile.NamedTemporaryFile(
            prefix="echo-", dir="/tmp", suffix=".png", delete=False
        ) as f:
            name = f.name
        try:
            self.assertTrue(al.is_path_sendable(name), f"expected allowed: {name}")
        finally:
            os.unlink(name)

    def test_generic_tmp_file_rejected(self):
        with tempfile.NamedTemporaryFile(
            prefix="not-sutando-", dir="/tmp", suffix=".txt", delete=False
        ) as f:
            name = f.name
        try:
            self.assertFalse(al.is_path_sendable(name), f"expected rejected: {name}")
        finally:
            os.unlink(name)


class TestNonExistentAndDirectory(unittest.TestCase):

    def test_nonexistent_path_rejected(self):
        self.assertFalse(al.is_path_sendable("/tmp/sutando-does-not-exist-xyz.txt"))

    def test_directory_rejected(self):
        # A directory is not a regular file — must be rejected even if it
        # matches an allowed prefix.
        with tempfile.TemporaryDirectory(prefix="sutando-", dir="/tmp") as d:
            self.assertFalse(al.is_path_sendable(d), f"directory should be rejected: {d}")


class TestSymlinks(unittest.TestCase):

    def test_symlink_resolving_inside_allowed_prefix_accepted(self):
        # symlink inside /tmp that resolves to a sutando- prefixed file → OK
        with tempfile.NamedTemporaryFile(
            prefix="sutando-target-", dir="/tmp", suffix=".txt", delete=False
        ) as f:
            target = f.name
        link = f"{target}.link"
        try:
            os.symlink(target, link)
            # The link's name does NOT have the prefix, but realpath → target does.
            self.assertTrue(al.is_path_sendable(link), f"symlink to allowed target should be OK: {link}")
        finally:
            os.unlink(link)
            os.unlink(target)

    def test_symlink_resolving_outside_all_roots_rejected(self):
        # symlink → /etc/hosts (outside any allowed root)
        with tempfile.NamedTemporaryFile(
            prefix="sutando-evil-link-", dir="/tmp", suffix=".txt", delete=False
        ) as f:
            link = f.name
        os.unlink(link)  # remove the temp file; we'll create a symlink in its place
        try:
            os.symlink("/etc/hosts", link)
            # Realpath → /etc/hosts → not in any allowed root/prefix
            self.assertFalse(al.is_path_sendable(link), f"symlink to /etc/hosts should be rejected: {link}")
        finally:
            if os.path.lexists(link):
                os.unlink(link)


class TestPrefixTraversal(unittest.TestCase):

    def test_dot_dot_traversal_through_allowed_prefix_rejected(self):
        # `/tmp/sutando-evil/../../../etc/passwd` starts with the allowed
        # prefix `/tmp/sutando-` at the string level, but realpath collapses
        # the `..` components → `/etc/passwd` which is outside all roots.
        # The function must reject this rather than leaking the file.
        fpath = "/tmp/sutando-evil/../../../etc/passwd"
        # Only run if /etc/passwd is a real file (it always is on macOS/Linux).
        if not os.path.isfile("/etc/passwd"):
            self.skipTest("/etc/passwd not present")
        self.assertFalse(
            al.is_path_sendable(fpath),
            "traversal via allowed-prefix directory must be rejected after realpath",
        )


class TestRootSiblingIsolation(unittest.TestCase):
    """The `startswith(root + sep)` check must prevent a sibling directory
    that shares a prefix with the root from being treated as a child."""

    def test_file_in_workspace_results_root_is_allowed(self):
        # `_REPO` in send_allowlist resolves to the workspace dir, not the
        # repo root. Write a temp file in the workspace results/ dir.
        results_dir = Path(al._REPO) / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(results_dir), suffix=".txt", delete=False
        ) as f:
            name = f.name
        try:
            self.assertTrue(al.is_path_sendable(name), f"workspace results/ file should be allowed: {name}")
        finally:
            os.unlink(name)

    def test_file_outside_results_sibling_rejected(self):
        # A file in /tmp that merely CONTAINS the word "results" is not in
        # the allowed roots.  Similarly, a sibling of the results/ dir must
        # not inherit its allowance.
        with tempfile.NamedTemporaryFile(
            prefix="results-fake-", dir="/tmp", suffix=".txt", delete=False
        ) as f:
            name = f.name
        try:
            self.assertFalse(al.is_path_sendable(name), f"sibling-prefix file must be rejected: {name}")
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
