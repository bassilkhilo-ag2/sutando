#!/usr/bin/env python3
"""Security regression guard: `_safe_path` path-traversal defence in agent-api.py.

`_safe_path(base_dir, filename)` is the CodeQL-recognised two-stage path-injection
guard: it strips all chars outside `[a-zA-Z0-9_.-]`, then uses `os.path.realpath`
+ `str.startswith(base + sep)` to prevent directory escape.

## Security model

The primary defence is the character whitelist: `/`, `\`, `\0`, and all other
path-separator / shell-special chars are stripped before `realpath` is called.
This makes path traversal impossible regardless of what the caller passes.
`realpath` + `startswith` is defence-in-depth (the CodeQL-modelled pair that
closes the `py/path-injection` query).

Pins:
  1. A normal task ID (`task-1234567890`) resolves to `<base>/task-1234567890.txt`.
  2. Slash-based traversal (`/etc/passwd`) — slashes stripped → resolves inside base.
  3. Backslash traversal (`..\\..\\etc\\passwd`) — backslashes stripped → inside base.
  4. A filename composed entirely of stripped chars (e.g. `!@#$%`) returns None.
  5. An empty string returns None.
  6. A null byte is stripped harmlessly; remaining chars resolve normally.
  7. `_safe_path` always appends `.txt` to the sanitised name.
  8. The returned path is absolute (realpath-normalised).
  9. All whitelisted chars (a-z A-Z 0-9 _ - .) pass through intact.
  10. Dots in `..` survive the filter as `..` + `.txt` = `...txt` inside base
      (traversal is impossible because `/` is already stripped).
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


api = _load("agent_api", REPO / "src" / "agent-api.py")

# A stable, non-existent base dir — realpath normalises even for absent paths.
BASE = Path(os.path.realpath("/tmp/sutando-safe-path-test-dir"))


def test_normal_task_id_resolves_inside_base():
    result = api._safe_path(BASE, "task-1234567890")
    assert result is not None, "expected a Path, got None"
    expected = BASE / "task-1234567890.txt"
    assert result == expected, f"expected {expected}, got {result}"


def test_slash_traversal_stripped_resolves_inside_base():
    # `/etc/passwd` → strip `/` → `etcpasswd` → `<base>/etcpasswd.txt`
    result = api._safe_path(BASE, "/etc/passwd")
    assert result is not None, "stripped slash-traversal should resolve inside base"
    assert str(result).startswith(str(BASE) + os.sep), f"escaped base: {result}"
    assert "etcpasswd" in str(result)


def test_backslash_traversal_stripped_resolves_inside_base():
    # Windows-style `..\\..\\etc\\passwd` → backslashes stripped → inside base
    result = api._safe_path(BASE, "..\\..\\etc\\passwd")
    assert result is not None, "stripped backslash-traversal should resolve inside base"
    assert str(result).startswith(str(BASE) + os.sep), f"escaped base: {result}"


def test_dot_dot_stays_inside_base():
    # `..` passes the char filter as `..`, becomes `...txt` inside base — not None.
    # Traversal is impossible because `/` is stripped; realpath sees no separator.
    result = api._safe_path(BASE, "..")
    assert result is not None, "'..' (no slash) should resolve inside base as '...txt'"
    assert str(result).startswith(str(BASE) + os.sep), f"escaped base: {result}"
    assert str(result).endswith(".txt")


def test_all_special_chars_returns_none():
    result = api._safe_path(BASE, "!@#$%^&*()")
    assert result is None, f"expected None for all-special, got {result!r}"


def test_empty_string_returns_none():
    result = api._safe_path(BASE, "")
    assert result is None, "expected None for empty string"


def test_null_byte_stripped_harmlessly():
    # Null byte is not in whitelist → stripped; remaining chars resolve normally.
    result = api._safe_path(BASE, "task\x001234")
    assert result is not None, "expected a Path after null-byte strip"
    assert "task1234" in str(result)
    assert str(result).startswith(str(BASE) + os.sep)


def test_result_always_ends_with_txt():
    result = api._safe_path(BASE, "task-abc")
    assert result is not None
    assert str(result).endswith(".txt"), f"expected .txt suffix, got {result}"


def test_result_is_absolute():
    result = api._safe_path(BASE, "task-xyz")
    assert result is not None
    assert result.is_absolute(), f"expected absolute path, got {result}"


def test_all_whitelisted_chars_pass_through():
    # a-z A-Z 0-9 _ - . are all allowed; verify they survive the filter.
    name = "Task_Result-2026.06.05"
    result = api._safe_path(BASE, name)
    assert result is not None, f"expected a Path for fully-whitelisted name {name!r}"
    assert name in str(result), f"whitelisted chars were stripped: {result}"


def main():
    tests = [
        test_normal_task_id_resolves_inside_base,
        test_slash_traversal_stripped_resolves_inside_base,
        test_backslash_traversal_stripped_resolves_inside_base,
        test_dot_dot_stays_inside_base,
        test_all_special_chars_returns_none,
        test_empty_string_returns_none,
        test_null_byte_stripped_harmlessly,
        test_result_always_ends_with_txt,
        test_result_is_absolute,
        test_all_whitelisted_chars_pass_through,
    ]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"All {len(tests)} _safe_path security tests passed.")


if __name__ == "__main__":
    main()
