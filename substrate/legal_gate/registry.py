"""Banned-corpora registry for the Sprint 18 retrieval-time legal gate.

Per `docs/master-product-spec.md` §9 the legal gate enforces the
Bartz / Hachette / AG MDL banned-corpus restrictions. This module
is the **operator-edited registry of what is banned** — five
parallel typed tuples that the `predicate.py` matchers consult.

Schema:

  - ``BANNED_DOMAINS``: hostnames whose content cannot be ingested
    regardless of which path discovers them. Examples (operator-
    populated post-lawyer-review): pirate-library hosts, mirrors
    of takedown-targeted aggregators. Match is suffix-aware so an
    entry of ``"example.com"`` blocks both ``example.com`` and
    ``mirror.example.com``.

  - ``BANNED_CORPUS_IDS``: source-corpus identifiers (e.g.
    ``"books3"``, ``"bookcorpus"``, ``"libgen-2023-08"``) that some
    ingestion paths may attach to a document. The gate refuses any
    document whose ``source_corpus`` metadata matches.

  - ``BANNED_AUTHORS``: case-folded author-substring matches. An
    entry of ``"Margaret Atwood"`` rejects documents whose
    ``author`` metadata contains the substring (case-insensitive).
    Substring rather than equality so per-publisher variations of
    the same author name still match.

  - ``BANNED_TITLE_SUBSTRINGS``: case-folded title-substring
    matches. Tighter than author because false positives are
    likelier; only used for titles narrow enough to disambiguate
    (e.g. a unique novel title rather than ``"Notes"``).

  - ``BANNED_CONTENT_HASH_PREFIXES``: SHA-256 hex prefixes (typically
    8-16 chars) on the canonical content_hash. Used for AG MDL
    where specific fingerprints are restricted regardless of
    domain or attribution.

**The seed registry is empty.** Adding entries requires a PR with
documented legal justification (Bartz / Hachette / AG MDL court
order citation, takedown notice reference, or equivalent). The
operator-or-lawyer review is the legal-defensibility moat; auto-
learning entries from observed takedowns is explicitly rejected
because it dilutes the cite-able provenance of each entry.

If the registry grows past ~200 entries, move to a JSON sidecar
under ``~/.antiek/legal_gate/registry.json`` so the operator can
edit without code review. For now the lawyer-review requirement
favors code-as-data.
"""

from __future__ import annotations

# ── Banned hostnames (suffix-matched) ─────────────────────────────
BANNED_DOMAINS: tuple[str, ...] = (
    # Empty seed. Each entry MUST cite the court order, takedown
    # notice, or lawyer-reviewed source that justifies inclusion.
    # Examples of the entry shape, kept commented out:
    #
    # "libgen.is",       # cite: ...
    # "z-lib.is",        # cite: ...
)


# ── Banned source-corpus identifiers ──────────────────────────────
BANNED_CORPUS_IDS: tuple[str, ...] = (
    # Examples of the entry shape:
    #
    # "books3",          # cite: AG MDL ECF No. ...
    # "bookcorpus",      # cite: ...
)


# ── Banned author substrings (case-folded) ────────────────────────
BANNED_AUTHORS: tuple[str, ...] = (
    # Authors whose works are subject to active restriction. Each
    # entry MUST carry the citing court order or settlement
    # reference in a code comment so it's discoverable in the
    # registry's git blame.
)


# ── Banned title substrings (case-folded) ─────────────────────────
BANNED_TITLE_SUBSTRINGS: tuple[str, ...] = (
    # Tighter than author. Only titles narrow enough to
    # disambiguate (unique novels, specific journal articles).
)


# ── Banned content-hash prefixes (sha256 hex, typically 8-16 chars) ─
BANNED_CONTENT_HASH_PREFIXES: tuple[str, ...] = (
    # For AG MDL fingerprint-based matching. Compute via
    # ``content_hash[:N]`` where N matches the operator's chosen
    # collision-probability vs registry-size tradeoff. 8 chars
    # collides at ~2^32 — sufficient for the projected registry
    # size; 12 chars at ~2^48 if the registry grows.
)


__all__ = [
    "BANNED_DOMAINS",
    "BANNED_CORPUS_IDS",
    "BANNED_AUTHORS",
    "BANNED_TITLE_SUBSTRINGS",
    "BANNED_CONTENT_HASH_PREFIXES",
]
