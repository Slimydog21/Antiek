"""Data island: embed + extract the canonical doc-model (HPRJ SPR-02 / M3).

The projection embeds the canonical doc-model JSON inside an inert
``<template data-antiek="doc-model" data-schema-version="1">`` element.
A ``<template>`` is parsed by the HTML parser but not rendered (its
content is inert), which gives a free, script-free container for the
round-trip payload. This is the load-bearing choice that lets the island
coexist with the SCRIPT-FREE invariant — see ``escape.py`` for why
``<template>`` and not ``<script type="application/json">``.

ROUND-TRIP PROPERTY (M3 gate): ``extract_island(embed_island(d)) == d``
for every doc-model ``d``. This holds over the golden corpus AND an
adversarial escaping corpus (``</template>`` inside strings, nested
``<template>``-looking substrings, unicode, quotes). The escaping regime
(``escape.island_escape``) makes the JSON survive an HTML parse and
``island_unescape`` is its exact inverse.

SCHEMA VERSIONING: the island carries ``data-schema-version``. The
extractor REJECTS an unknown version with a typed error
(``UnknownIslandSchemaVersion``) — a projection written by a future
schema-2 renderer must not be silently mis-parsed by a schema-1
extractor. This mirrors the ``.antiek`` container's version policy
(SPEC.md §7: major-mismatch refuses) so the island and the container
agree on how to handle version skew.

DETERMINISM: the island bytes are a pure function of (doc-model,
schema_version). JSON is serialised with ``sort_keys=True`` and
``ensure_ascii=False`` (stable UTF-8) — no dict-iteration-order variance,
no ascii-folding variance. No wall-clock.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .escape import island_escape, island_unescape

# The schema version this sprint ships. Bump on incompatible island-shape
# changes. The extractor's rejection policy is major-version-scoped: a
# different major version is refused; within-major additions are forward-
# compatible (the extractor preserves unknown keys — but for SPR-02 there
# is only "1").
ISLAND_SCHEMA_VERSION: str = "1"

_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1"})


class IslandError(Exception):
    """Base class for data-island errors."""


class UnknownIslandSchemaVersion(IslandError):
    """The island carries a ``data-schema-version`` the extractor does
    not support. Raised (not silenced) so a caller never silently
    mis-parses a future-schema island. The offending version is on
    ``.version``."""

    def __init__(self, version: str) -> None:
        super().__init__(
            f"extract_island: unsupported data-schema-version {version!r}; "
            f"supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
        )
        self.version = version


class IslandNotFound(IslandError):
    """No ``<template data-antiek="doc-model">`` element found in the
    HTML. Raised so a caller can distinguish "missing island" from
    "malformed island"."""

    def __init__(self) -> None:
        super().__init__(
            "extract_island: no <template data-antiek=\"doc-model\"> "
            "element found in the HTML"
        )


class MalformedIsland(IslandError):
    """The island element was found but its content could not be parsed
    as JSON (after unescaping). Indicates corruption or a writer bug."""


# ── Embedding ──


def embed_island(
    doc_model: dict[str, Any], *, schema_version: str = ISLAND_SCHEMA_VERSION
) -> str:
    """Render the data-island HTML fragment for ``doc_model``.

    Returns the full ``<template ...>...</template>`` element as a string.
    The renderer inserts this into the document body. The JSON is
    canonicalised (sorted keys, ensure_ascii=False) before escaping so
    two renders of the same doc-model produce byte-identical island bytes.

    Parameters
    ----------
    doc_model:
        The canonical doc-model dict (the TipTap doc + any manifest
        provenance the renderer was given). Embedded verbatim (after
        JSON canonicalisation + island escaping).
    schema_version:
        The data-schema-version to stamp. Defaults to
        ``ISLAND_SCHEMA_VERSION`` ("1"). A caller rendering a future
        schema passes its own version; the extractor will refuse it
        under a schema-1 reader.
    """
    canonical = json.dumps(
        doc_model, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    escaped = island_escape(canonical)
    return (
        f'<template data-antiek="doc-model" '
        f'data-schema-version="{schema_version}">{escaped}</template>'
    )


# ── Extraction ──

# Match the island element. The data-antiek attribute value is fixed
# ("doc-model"); the data-schema-version is captured. We allow arbitrary
# whitespace and attribute order robustness by matching the two
# attributes in either order. The content between > and </template> is
# captured non-greedily. The regex is case-SENSITIVE on the tag name
# "template" and the attribute names — the renderer always emits
# lowercase, and a case-mismatched island is a corruption signal we'd
# rather catch than silently normalise. (The zero-script gate separately
# case-folds for script detection; the island extractor does not need to.)
_ISLAND_RE = re.compile(
    r'<template\b[^>]*\bdata-antiek="doc-model"[^>]*>'
    r'(.*?)'
    r'</template>',
    re.DOTALL,
)
_SCHEMA_VERSION_RE = re.compile(r'\bdata-schema-version="([^"]*)"')


def extract_island(html: str) -> dict[str, Any]:
    """Extract and parse the doc-model from a projection's data island.

    Round-trip property: ``extract_island(embed_island(d)) == d``.

    Raises
    ------
    IslandNotFound
        No island element present.
    UnknownIslandSchemaVersion
        Island present but ``data-schema-version`` is not supported.
    MalformedIsland
        Island present but content is not valid JSON after unescaping.
    """
    match = _ISLAND_RE.search(html)
    if match is None:
        raise IslandNotFound()
    raw_content = match.group(1)

    # Find the schema version. Search the full matched element (the
    # opening tag) — the regex above captured only the content, so we
    # re-scan the opening tag region. The opening tag ends at the first
    # '>' after <template; locate it.
    open_tag_end = match.group(0).index(">") + 1
    open_tag = match.group(0)[:open_tag_end]
    sv_match = _SCHEMA_VERSION_RE.search(open_tag)
    if sv_match is None:
        # No schema version on the island. Treat as unknown — a writer
        # must stamp one. Refuse rather than guess.
        raise UnknownIslandSchemaVersion("<missing>")
    version = sv_match.group(1)
    if version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise UnknownIslandSchemaVersion(version)

    unescaped = island_unescape(raw_content)
    try:
        doc_model = json.loads(unescaped)
    except json.JSONDecodeError as e:
        raise MalformedIsland(
            f"extract_island: island content is not valid JSON: {e}"
        ) from e
    if not isinstance(doc_model, dict):
        raise MalformedIsland(
            f"extract_island: island content parsed to "
            f"{type(doc_model).__name__}, expected object"
        )
    return doc_model


__all__ = [
    "ISLAND_SCHEMA_VERSION",
    "IslandError",
    "IslandNotFound",
    "MalformedIsland",
    "UnknownIslandSchemaVersion",
    "embed_island",
    "extract_island",
]
