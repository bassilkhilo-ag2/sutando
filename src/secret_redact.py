"""Inbound-message secret redaction — Phase 1 (#1354).

Scans text for known secret patterns and replaces them with
[REDACTED:<TYPE>] placeholders so secrets never land in task files.

Usage:
    from secret_redact import redact_secrets
    clean, found = redact_secrets(raw_message_text)
    if found:
        print(f"[secret-redact] redacted: {', '.join(found)}", flush=True)

Returns (redacted_text, list_of_detected_type_strings).
The list is empty when no secrets were found.

Phase 1 scope: detect-and-redact only (no buffer, no interactive flow).
Interactive "store as which key?" follow-up is Phase 2 (#1354).
"""
from __future__ import annotations

import re
from typing import NamedTuple


class _Pattern(NamedTuple):
    name: str
    pattern: re.Pattern[str]


# Ordered longest-first to avoid partial matches leaving fragments.
_PATTERNS: list[_Pattern] = [
    # Anthropic API keys  (sk-ant-api03-... etc.)
    _Pattern("anthropic-key",
             re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}", re.ASCII)),
    # OpenAI project keys  (sk-proj-...)
    _Pattern("openai-project-key",
             re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}", re.ASCII)),
    # OpenAI legacy service keys  (sk-...)
    _Pattern("openai-key",
             re.compile(r"sk-[A-Za-z0-9]{20,}", re.ASCII)),
    # GitHub personal access tokens (classic: ghp_; fine-grained: github_pat_)
    _Pattern("github-token",
             re.compile(r"(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9]{20,}", re.ASCII)),
    # AWS Access Key ID
    _Pattern("aws-access-key-id",
             re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])", re.ASCII)),
    # Slack bot / user / app tokens
    _Pattern("slack-token",
             re.compile(r"xox[bpars]-[0-9A-Za-z][0-9A-Za-z-]{8,}", re.ASCII)),
    # PEM private key block (single-line or multi-line)
    _Pattern("pem-private-key",
             re.compile(r"-----BEGIN\s+(?:\w+ )*PRIVATE KEY-----[\s\S]*?-----END\s+(?:\w+ )*PRIVATE KEY-----",
                        re.MULTILINE)),
    # JWT  (three base64url segments separated by dots; min 20 chars per segment)
    _Pattern("jwt",
             re.compile(r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}", re.ASCII)),
    # Google API keys  (AIza...)
    _Pattern("google-api-key",
             re.compile(r"AIza[0-9A-Za-z_-]{35}", re.ASCII)),
    # Stripe secret keys  (sk_live_... or sk_test_...)
    _Pattern("stripe-secret-key",
             re.compile(r"sk_(?:live|test)_[0-9A-Za-z]{24,}", re.ASCII)),
    # Twilio auth tokens (32 lowercase hex chars, typically after Account SID context)
    # Too noisy without a label. Skip standalone hex strings — too many FPs.
]


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Replace known secret patterns with [REDACTED:<TYPE>] placeholders.

    Returns:
        (redacted_text, detected_type_names)
        detected_type_names is empty when nothing was found.
    """
    if not text:
        return text, []

    found: list[str] = []
    result = text
    for p in _PATTERNS:
        if p.pattern.search(result):
            result = p.pattern.sub(f"[REDACTED:{p.name}]", result)
            found.append(p.name)
    return result, found
