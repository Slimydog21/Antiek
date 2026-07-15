"""Pure matching helpers for the Sprint 18 retrieval-time legal gate.

Per `docs/master-product-spec.md` §9: the gate is enforced at the
SQL-WHERE level inside substrate query paths AND at the
``check_url`` seam for the discovery layer. This module is the
**pure-function half** — given a URL / metadata bundle and the
registry tuples from `registry.py`, return whether the entity is
banned and why.

Pure means: no DB, no env, no time-dependent behavior. The matchers
are easily testable and easy to reason about. The `gate.py` module
threads these into the `LegalGate` Protocol surface and applies
them at the appropriate seams.

Match semantics are deliberately permissive on input (case folding,
substring matching, suffix matching for hosts) and tight on what
counts as "banned" (each registry tuple has a specific shape; no
fuzzy fallback). The asymmetry is intentional — adding a false
negative is worse than a false positive on a curated registry.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from . import registry

# ── URL / domain matching ─────────────────────────────────────────


def _normalize_host(host: str) -> str:
    """Lowercase + strip a leading ``www.``. Empty / malformed
    hosts return as-is so the caller can treat the unmatched-empty
    case explicitly."""
    h = host.strip().lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def host_matches_banned_domain(
    host: str, banned: Iterable[str] = None,
) -> str | None:
    """Return the matching banned-domain entry if ``host`` is on
    or below any banned suffix. None otherwise.

    Match is suffix-aware: a banned entry ``"example.com"`` matches
    ``example.com`` and ``mirror.example.com`` but NOT
    ``"badexample.com"`` (the latter is a different domain that
    happens to share a string suffix).
    """
    if banned is None:
        banned = registry.BANNED_DOMAINS
    h = _normalize_host(host)
    if not h:
        return None
    for b in banned:
        b_norm = _normalize_host(b)
        if not b_norm:
            continue
        if h == b_norm or h.endswith("." + b_norm):
            return b
    return None


def url_blocked_reason(
    url: str,
    *,
    banned_domains: Iterable[str] = None,
) -> str | None:
    """Return a human-readable rejection reason if the URL's host
    is on the banned list. None if allowed.

    Designed for the `LegalGate.check_url` seam — the discovery
    layer's `promote_discovery` calls this exact function indirectly
    via the gate."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.netloc:
        return None
    match = host_matches_banned_domain(parsed.netloc, banned_domains)
    if match:
        return f"banned domain: {match}"
    return None


# ── Metadata matching (document-level) ────────────────────────────


def _ci_substring_match(
    needle: str, haystacks: Iterable[str],
) -> str | None:
    """Case-insensitive substring search. Returns the matching
    needle (the banned entry) on hit, None otherwise."""
    if not needle:
        return None
    nlc = needle.casefold()
    for h in haystacks:
        if not h:
            continue
        if h.casefold() in nlc:
            return h
    return None


def author_blocked_reason(
    author: str, banned: Iterable[str] = None,
) -> str | None:
    """Author substring match against `BANNED_AUTHORS`. Returns
    the matching banned entry on hit (so the audit trail records
    which registry entry triggered)."""
    if banned is None:
        banned = registry.BANNED_AUTHORS
    match = _ci_substring_match(author or "", banned)
    if match:
        return f"banned author: {match}"
    return None


def title_blocked_reason(
    title: str, banned: Iterable[str] = None,
) -> str | None:
    """Title substring match against `BANNED_TITLE_SUBSTRINGS`."""
    if banned is None:
        banned = registry.BANNED_TITLE_SUBSTRINGS
    match = _ci_substring_match(title or "", banned)
    if match:
        return f"banned title substring: {match}"
    return None


def corpus_blocked_reason(
    source_corpus: str, banned: Iterable[str] = None,
) -> str | None:
    """Exact (case-folded) match against `BANNED_CORPUS_IDS`.
    Source-corpus identifiers are programmatic; exact match avoids
    accidental over-blocking on naming variations."""
    if banned is None:
        banned = registry.BANNED_CORPUS_IDS
    if not source_corpus:
        return None
    sc = source_corpus.strip().casefold()
    for b in banned:
        if not b:
            continue
        if b.strip().casefold() == sc:
            return f"banned corpus id: {b}"
    return None


def content_hash_blocked_reason(
    content_hash: str, banned: Iterable[str] = None,
) -> str | None:
    """Hex-prefix match. Strips any ``"sha256:"`` algorithm prefix
    so callers can pass the raw payload field unchanged."""
    if banned is None:
        banned = registry.BANNED_CONTENT_HASH_PREFIXES
    if not content_hash:
        return None
    h = content_hash.strip().lower()
    if h.startswith("sha256:"):
        h = h[len("sha256:"):]
    for prefix in banned:
        if not prefix:
            continue
        p = prefix.strip().lower()
        if p and h.startswith(p):
            return f"banned content hash prefix: {p}"
    return None


def document_blocked_reason(
    *,
    url: str | None = None,
    author: str | None = None,
    title: str | None = None,
    source_corpus: str | None = None,
    content_hash: str | None = None,
    banned_domains: Iterable[str] = None,
    banned_corpus_ids: Iterable[str] = None,
    banned_authors: Iterable[str] = None,
    banned_title_substrings: Iterable[str] = None,
    banned_content_hash_prefixes: Iterable[str] = None,
) -> str | None:
    """Compose all matchers. Returns the FIRST matching reason in
    a stable order (domain → corpus → author → title → hash) so
    the audit trail is deterministic.

    Callers pass only the fields they have; missing fields are
    skipped. A document with no provenance fields is allowed by
    default (the registry has nothing to match against)."""
    if url:
        r = url_blocked_reason(url, banned_domains=banned_domains)
        if r:
            return r
    if source_corpus:
        r = corpus_blocked_reason(source_corpus, banned_corpus_ids)
        if r:
            return r
    if author:
        r = author_blocked_reason(author, banned_authors)
        if r:
            return r
    if title:
        r = title_blocked_reason(title, banned_title_substrings)
        if r:
            return r
    if content_hash:
        r = content_hash_blocked_reason(
            content_hash, banned_content_hash_prefixes
        )
        if r:
            return r
    return None


__all__ = [
    "author_blocked_reason",
    "content_hash_blocked_reason",
    "corpus_blocked_reason",
    "document_blocked_reason",
    "host_matches_banned_domain",
    "title_blocked_reason",
    "url_blocked_reason",
]
