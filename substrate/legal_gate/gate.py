"""Registry-backed LegalGate implementation.

Replaces the Sprint-17 `PermissiveLegalGate` placeholder as the
default returned by `default_legal_gate()`. Threads registry +
predicate together so the upstream callers (Wedge 1 promote path,
future substrate read/write paths) get real Bartz / Hachette /
AG MDL enforcement.

Per spec `docs/master-product-spec.md` §9: the broader Sprint 18
gate also enforces at the SQL-WHERE level inside graph reads and
writes. That refactor touches every documents/chunks query path
and is out of scope of this module. This module is the
**URL-checking half** — the seam Wedge 1 routes through.

When the operator/lawyer adds entries to `registry.py`, this gate
starts rejecting them. The empty seed registry means the default
behavior is identical to the placeholder until entries are added —
but the substrate is correct, so the addition is a pure-data
change rather than an architecture change.
"""

from __future__ import annotations

from . import registry
from .predicate import document_blocked_reason, url_blocked_reason

# Local import-free re-declarations — defined in __init__.py and
# imported lazily inside class methods to avoid an import cycle
# between gate.py and __init__.py.


class RegistryBackedLegalGate:
    """Real-registry-consulting `LegalGate`. Stateless apart from
    the module-level registry tuples, which are import-time
    constants.

    The default constructor consults the module-level registry.
    Tests may inject a frozen-snapshot tuple for deterministic
    behavior independent of any concurrent registry edits.
    """

    def __init__(
        self,
        *,
        banned_domains=None,
        banned_corpus_ids=None,
        banned_authors=None,
        banned_title_substrings=None,
        banned_content_hash_prefixes=None,
    ) -> None:
        # None → consult the module-level registry. Explicit
        # injection (even an empty tuple) overrides — useful for
        # tests that want a deterministic state independent of any
        # registry mutations elsewhere in the run.
        self._banned_domains = (
            banned_domains if banned_domains is not None
            else registry.BANNED_DOMAINS
        )
        self._banned_corpus_ids = (
            banned_corpus_ids if banned_corpus_ids is not None
            else registry.BANNED_CORPUS_IDS
        )
        self._banned_authors = (
            banned_authors if banned_authors is not None
            else registry.BANNED_AUTHORS
        )
        self._banned_title_substrings = (
            banned_title_substrings if banned_title_substrings is not None
            else registry.BANNED_TITLE_SUBSTRINGS
        )
        self._banned_content_hash_prefixes = (
            banned_content_hash_prefixes if banned_content_hash_prefixes is not None
            else registry.BANNED_CONTENT_HASH_PREFIXES
        )

    def check_url(self, url: str):
        """Implements the `LegalGate.check_url` protocol method.

        Today checks only the URL's host against
        `BANNED_DOMAINS`. The fuller `check_document(...)` surface
        (author/title/corpus/hash) lives below for callers that
        have the metadata bundle at the time of the check.

        Returns a `LegalGateVerdict` with `gate_kind="sql_where_registry"`
        regardless of decision — the verdict shape stays the same
        so the trajectory log can tell which gate variant ran.
        """
        # Local import to break the cycle between __init__.py and
        # gate.py — the LegalGateVerdict dataclass is exported by
        # the package init.
        from . import LegalGateVerdict

        reason = url_blocked_reason(url, banned_domains=self._banned_domains)
        if reason is None:
            return LegalGateVerdict(
                allowed=True, reason=None, gate_kind="sql_where_registry"
            )
        return LegalGateVerdict(
            allowed=False, reason=reason, gate_kind="sql_where_registry"
        )

    def check_document(
        self,
        *,
        url: str = "",
        author: str = "",
        title: str = "",
        source_corpus: str = "",
        content_hash: str = "",
    ):
        """Fuller-metadata check. Used by ingestion paths that have
        author/title/corpus/hash at the time of the gate
        consultation. Routes through the full `document_blocked_reason`
        predicate — returns on the first match (deterministic order:
        domain → corpus → author → title → hash).
        """
        from . import LegalGateVerdict

        reason = document_blocked_reason(
            url=url,
            author=author,
            title=title,
            source_corpus=source_corpus,
            content_hash=content_hash,
            banned_domains=self._banned_domains,
            banned_corpus_ids=self._banned_corpus_ids,
            banned_authors=self._banned_authors,
            banned_title_substrings=self._banned_title_substrings,
            banned_content_hash_prefixes=self._banned_content_hash_prefixes,
        )
        if reason:
            return LegalGateVerdict(
                allowed=False, reason=reason, gate_kind="sql_where_registry"
            )
        return LegalGateVerdict(
            allowed=True, reason=None, gate_kind="sql_where_registry"
        )


__all__ = ["RegistryBackedLegalGate"]
