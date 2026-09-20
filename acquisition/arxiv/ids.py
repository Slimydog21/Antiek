"""arXiv identifier parsing — robust, version-aware, error-feed-aware.

Consolidates id handling that was previously an ad-hoc ``full_id.split("v")[0]``
in :mod:`acquisition.arxiv.client`. That split is fragile: it partitions on the
FIRST ``v`` anywhere in the string, so it only works by luck for modern ids and
gives a wrong base for any id whose non-version portion could contain a ``v``.
This module anchors the version suffix to ``vN`` at END-of-string, matching the
discipline of the ``~/.claude/skills/arxiv`` port (``normalize_arxiv_id`` /
``ARXIV_ID_RE``) so the platform and the skill agree on what a valid id is.

Two arXiv id shapes:
  * new style  ``2402.03300``            (YYMM.NNNNN, 4 or 5 trailing digits)
  * old style  ``hep-th/0601001``        (``archive[.SUBJ]/YYMMNNN``, 7 digits)
either optionally suffixed with an explicit version ``v<N>``.

Also exposes :func:`looks_like_error_feed`: arXiv's Atom API answers a malformed
query with a 200 whose single ``<entry>`` has an id like
``http://arxiv.org/api/errors#…``. Parsing that as a paper mints a garbage
record; callers use this to reject the entry instead.
"""

from __future__ import annotations

import re

# Matches a full arXiv id (base only, no version, no version tolerated here) —
# mirrors the skill's ARXIV_ID_RE so validation is identical on both sides.
ARXIV_ID_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})$",
)

# Splits a (possibly version-suffixed) id into (base, version). The version group
# is anchored to the END of the string as ``v`` followed by digits, so the base
# is everything before a trailing ``vN`` — never a mid-string ``v``. ``base`` is
# non-greedy so the trailing ``vN`` is preferentially assigned to the version
# group when present.
_VERSION_RE = re.compile(r"^(?P<base>.+?)(?P<ver>v\d+)?$")

# The sentinel host arXiv uses in its Atom error feed <id> element.
_ERROR_FEED_MARKER = "/api/errors"


def split_id_version(full_id: str) -> tuple[str, str]:
    """Split ``2402.03300v2`` → ``("2402.03300", "v2")``.

    An id with no version suffix returns ``(id, "")``. The version, when present,
    RETAINS its leading ``v`` (``"v2"``, not ``"2"``) — matching the historical
    :class:`~acquisition.arxiv.client.ArxivPaper.version` contract.

    Unlike ``full_id.split("v")[0]`` this anchors the version to a trailing
    ``v\\d+``: ``hep-th/0601001`` (no version) is returned intact, and a base that
    happened to contain a ``v`` would not be truncated.
    """
    m = _VERSION_RE.match(full_id.strip())
    if m is None:  # pragma: no cover - .+? matches any non-empty string
        return full_id.strip(), ""
    return m.group("base"), (m.group("ver") or "")


def strip_version(full_id: str) -> str:
    """Return the base id with any trailing ``vN`` removed."""
    return split_id_version(full_id)[0]


def is_valid_arxiv_id(candidate: str) -> bool:
    """True iff ``candidate`` (base id, no version) is a well-formed arXiv id.

    Callers validate a CLI-supplied ``--ids`` value BEFORE any network call so a
    typo becomes a local error, not a wasted (rate-limited) request against the
    export API.
    """
    return bool(ARXIV_ID_RE.match((candidate or "").strip()))


def normalize_arxiv_id(raw: str, *, validate: bool = True) -> tuple[str, str]:
    """Normalize a user- or feed-supplied id reference to ``(base, version)``.

    Accepts bare ids, ``arxiv:2402.03300``, and full URLs
    (``https://arxiv.org/abs/2402.03300v2``, ``…/pdf/…``, ``…/html/…``). When
    ``validate`` is set the base must match :data:`ARXIV_ID_RE`, else
    :class:`ValueError` is raised — the pre-network guard the export-search path
    was missing.
    """
    ref = (raw or "").strip()
    if ref.lower().startswith("arxiv:"):
        ref = ref[len("arxiv:"):]
    # Pull the id out of an abs/pdf/html URL path.
    for sep in ("/abs/", "/pdf/", "/html/"):
        if sep in ref:
            ref = ref.split(sep, 1)[1]
            break
    ref = ref.rstrip("/")
    if ref.endswith(".pdf"):
        ref = ref[: -len(".pdf")]
    base, version = split_id_version(ref)
    if validate and not is_valid_arxiv_id(base):
        raise ValueError(f"not a well-formed arXiv id: {raw!r} (parsed base {base!r})")
    return base, version


def looks_like_error_feed(raw_id: str) -> bool:
    """True when an Atom ``<id>`` is arXiv's error-feed sentinel, not a paper.

    arXiv answers a malformed query with a 200 Atom feed whose single entry's
    ``<id>`` is ``http://arxiv.org/api/errors#…``; treating it as a paper mints a
    garbage record. Callers reject the entry (or the whole response) instead.
    """
    return _ERROR_FEED_MARKER in (raw_id or "")


__all__ = [
    "ARXIV_ID_RE",
    "split_id_version",
    "strip_version",
    "is_valid_arxiv_id",
    "normalize_arxiv_id",
    "looks_like_error_feed",
]
