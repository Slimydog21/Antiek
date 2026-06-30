"""Prompt-injection defense for the Antiek MCP server.

OWASP LLM01 mitigation: every public-notes return wraps content in
``<antiek:content trusted="false">...</antiek:content>`` so consuming
LLMs treat the payload as untrusted data rather than executable
instructions. Private notes are NOT wrapped — the owner's own content
is trusted.

Reference: OWASP Top 10 for LLM Applications (LLM01: Prompt Injection).
"""

from __future__ import annotations

import re

_OPEN_TAG = '<antiek:content trusted="false">'
_CLOSE_TAG = "</antiek:content>"

# Pre-compiled pattern for detecting existing wrapper (anchored, DOTALL).
_WRAPPER_RE: re.Pattern[str] = re.compile(
    r'^<antiek:content\s+trusted="false"\s*>(.*)</antiek:content>$',
    re.DOTALL,
)


def wrap_untrusted_content(content: str) -> str:
    """Wrap *content* in the untrusted-content envelope.

    Idempotent: if *content* is already wrapped, returns it unchanged.
    """
    if is_content_wrapped(content):
        return content
    return f"{_OPEN_TAG}{content}{_CLOSE_TAG}"


def is_content_wrapped(content: str) -> bool:
    """Return True if *content* is already inside an untrusted envelope."""
    return _WRAPPER_RE.match(content) is not None


def unwrap_content(content: str) -> str:
    """Extract the inner content from an untrusted envelope.

    Raises ``ValueError`` if *content* is not wrapped.
    """
    m = _WRAPPER_RE.match(content)
    if m is None:
        raise ValueError("Content is not wrapped in <antiek:content> envelope")
    return m.group(1)
