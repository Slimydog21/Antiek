"""Tests for the Sprint 18 retrieval-time legal gate.

Spec: `docs/master-product-spec.md` §9 + `docs/integration_exa_browserbase.md` §6.9.

Covers:
  - `predicate.py` pure matchers (URL/host, author, title, corpus,
    content_hash)
  - `RegistryBackedLegalGate` URL + document checks
  - `default_legal_gate()` factory branches:
      * default returns the real gate
      * ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1 returns the placeholder
      * ANTIEK_LEGAL_GATE_DISABLED=1 returns the placeholder with the
        acknowledgment auto-set
  - Backward compat: PermissiveLegalGate placeholder still requires
    the acknowledgment flag
"""

from __future__ import annotations

import pytest

from substrate.legal_gate import (
    LegalGatePlaceholderUnacknowledged,
    LegalGateVerdict,
    PermissiveLegalGate,
    RegistryBackedLegalGate,
    default_legal_gate,
)
from substrate.legal_gate.predicate import (
    author_blocked_reason,
    content_hash_blocked_reason,
    corpus_blocked_reason,
    document_blocked_reason,
    host_matches_banned_domain,
    title_blocked_reason,
    url_blocked_reason,
)

# ── predicate.host / url ──────────────────────────────────────────


def test_host_matches_exact_banned_domain():
    assert host_matches_banned_domain("libgen.is", banned=("libgen.is",)) == "libgen.is"


def test_host_matches_suffix_subdomain():
    """A banned `example.com` MUST match `mirror.example.com`."""
    assert host_matches_banned_domain(
        "mirror.example.com", banned=("example.com",)
    ) == "example.com"


def test_host_does_not_match_string_lookalike():
    """`badexample.com` is NOT on `example.com`'s suffix — different
    registered domain, should not match."""
    assert host_matches_banned_domain(
        "badexample.com", banned=("example.com",)
    ) is None


def test_host_strips_www_and_lowercases():
    assert host_matches_banned_domain(
        "WWW.Libgen.IS", banned=("libgen.is",)
    ) == "libgen.is"


def test_host_empty_string():
    assert host_matches_banned_domain("", banned=("libgen.is",)) is None


def test_host_against_empty_registry():
    assert host_matches_banned_domain("libgen.is", banned=()) is None


def test_url_blocked_reason_returns_reason():
    r = url_blocked_reason(
        "https://mirror.libgen.is/book/123",
        banned_domains=("libgen.is",),
    )
    assert r is not None
    assert "libgen.is" in r


def test_url_blocked_reason_allows_unbanned():
    r = url_blocked_reason(
        "https://arxiv.org/abs/2412.12345",
        banned_domains=("libgen.is",),
    )
    assert r is None


def test_url_blocked_reason_handles_malformed_url():
    """A non-URL string should not raise — returns None and the
    gate proceeds to the next signal."""
    assert url_blocked_reason("not a url", banned_domains=("x.com",)) is None
    assert url_blocked_reason("", banned_domains=("x.com",)) is None


# ── predicate: author / title / corpus / hash ─────────────────────


def test_author_blocked_substring_match():
    r = author_blocked_reason(
        "Margaret Atwood, et al.", banned=("Margaret Atwood",)
    )
    assert r is not None
    assert "Margaret Atwood" in r


def test_author_blocked_is_case_insensitive():
    r = author_blocked_reason("MARGARET ATWOOD", banned=("margaret atwood",))
    assert r is not None


def test_author_unmatched_returns_none():
    assert author_blocked_reason("Ursula K. Le Guin", banned=("Margaret Atwood",)) is None


def test_author_empty_input_returns_none():
    assert author_blocked_reason("", banned=("Margaret Atwood",)) is None


def test_title_blocked_substring_match():
    r = title_blocked_reason(
        "The Handmaid's Tale (annotated)", banned=("Handmaid's Tale",)
    )
    assert r is not None


def test_corpus_blocked_exact_match():
    r = corpus_blocked_reason("books3", banned=("books3", "bookcorpus"))
    assert r is not None
    assert "books3" in r


def test_corpus_does_not_substring_match():
    """Corpus identifiers are exact-match (programmatic). Substring
    behavior would over-block on naming variations."""
    assert corpus_blocked_reason("books3v2", banned=("books3",)) is None


def test_content_hash_prefix_match_strips_algorithm():
    """The payload's `content_hash` field is shaped like
    `sha256:<hex>`; the predicate strips the algorithm prefix."""
    r = content_hash_blocked_reason(
        "sha256:abcd1234567890ef",
        banned=("abcd1234",),
    )
    assert r is not None


def test_content_hash_no_match():
    assert content_hash_blocked_reason(
        "sha256:abcd1234", banned=("ffff",)
    ) is None


# ── predicate.document_blocked_reason composite ──────────────────


def test_document_blocked_returns_first_match_in_order():
    """Order: domain → corpus → author → title → hash. A document
    matching multiple should report the domain match first."""
    # Need to inject via registry monkeypatch.
    import substrate.legal_gate.predicate as predicate_mod  # noqa: F401
    from substrate.legal_gate import registry

    # Each banned tuple is a module-level constant; monkeypatch them
    # together via the registry module to test the composition.
    saved = (
        registry.BANNED_DOMAINS,
        registry.BANNED_AUTHORS,
        registry.BANNED_TITLE_SUBSTRINGS,
    )
    try:
        registry.BANNED_DOMAINS = ("libgen.is",)  # type: ignore[misc]
        registry.BANNED_AUTHORS = ("Margaret Atwood",)  # type: ignore[misc]
        registry.BANNED_TITLE_SUBSTRINGS = ("Handmaid",)  # type: ignore[misc]
        r = document_blocked_reason(
            url="https://libgen.is/x",
            author="Margaret Atwood",
            title="Handmaid's Tale",
        )
        assert r is not None
        assert "libgen.is" in r  # domain first
    finally:
        registry.BANNED_DOMAINS, registry.BANNED_AUTHORS, registry.BANNED_TITLE_SUBSTRINGS = saved  # type: ignore[misc]


def test_document_with_no_signals_allowed():
    """Empty input fields — nothing to match against."""
    assert document_blocked_reason() is None
    assert document_blocked_reason(url="", author="", title="") is None


# ── RegistryBackedLegalGate ──────────────────────────────────────


def test_registry_backed_gate_default_allows_when_empty_registry():
    g = RegistryBackedLegalGate(
        banned_domains=(),
        banned_authors=(),
        banned_corpus_ids=(),
        banned_title_substrings=(),
        banned_content_hash_prefixes=(),
    )
    v = g.check_url("https://example.com/anything")
    assert v.allowed is True
    assert v.gate_kind == "sql_where_registry"


def test_registry_backed_gate_blocks_known_domain():
    g = RegistryBackedLegalGate(banned_domains=("libgen.is",))
    v = g.check_url("https://mirror.libgen.is/book/123")
    assert v.allowed is False
    assert "libgen.is" in (v.reason or "")
    assert v.gate_kind == "sql_where_registry"


def test_registry_backed_gate_check_document_blocks_author():
    g = RegistryBackedLegalGate(banned_authors=("Margaret Atwood",))
    v = g.check_document(
        url="https://allowed-host.example/x",
        author="Margaret Atwood",
        title="Anything",
    )
    assert v.allowed is False
    assert "Margaret Atwood" in (v.reason or "")


def test_registry_backed_gate_check_document_passes_clean():
    g = RegistryBackedLegalGate(
        banned_domains=("libgen.is",),
        banned_authors=("Margaret Atwood",),
    )
    v = g.check_document(
        url="https://arxiv.org/abs/x",
        author="Ursula K. Le Guin",
        title="Unrelated",
    )
    assert v.allowed is True


def test_registry_backed_gate_composes_priorities_in_order():
    """When URL is banned AND author is banned, the URL match
    fires first (deterministic check_document order)."""
    g = RegistryBackedLegalGate(
        banned_domains=("libgen.is",),
        banned_authors=("Atwood",),
    )
    v = g.check_document(
        url="https://libgen.is/x", author="Margaret Atwood",
    )
    assert v.allowed is False
    assert "libgen.is" in (v.reason or "")


# ── default_legal_gate() factory ─────────────────────────────────


def test_default_factory_returns_real_gate(monkeypatch):
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_DISABLED", raising=False)
    g = default_legal_gate()
    assert isinstance(g, RegistryBackedLegalGate)
    v = g.check_url("https://example.com/x")
    # Empty seed registry → allowed.
    assert v.allowed is True
    assert v.gate_kind == "sql_where_registry"


def test_default_factory_disabled_returns_placeholder_bypassed(monkeypatch):
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")
    g = default_legal_gate()
    assert isinstance(g, PermissiveLegalGate)
    # Verdict's gate_kind reflects the placeholder for audit-trail
    # honesty.
    assert g.check_url("https://anything.example/x").gate_kind == "placeholder"


def test_default_factory_placeholder_acked_returns_placeholder(monkeypatch):
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_DISABLED", raising=False)
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    g = default_legal_gate()
    assert isinstance(g, PermissiveLegalGate)


def test_default_factory_disabled_takes_precedence_over_acked(monkeypatch):
    """If both env vars are set, ANTIEK_LEGAL_GATE_DISABLED wins —
    the disabled path auto-bypasses the acknowledgment requirement."""
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    g = default_legal_gate()
    assert isinstance(g, PermissiveLegalGate)


# ── PermissiveLegalGate backward compat ──────────────────────────


def test_placeholder_still_requires_ack(monkeypatch):
    """The Sprint 17 contract: PermissiveLegalGate() without the
    ack env raises. Unchanged by the Sprint 18 work."""
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    with pytest.raises(LegalGatePlaceholderUnacknowledged):
        PermissiveLegalGate()


def test_placeholder_bypass_for_tests_works():
    g = PermissiveLegalGate(_bypass_acknowledgment=True)
    v = g.check_url("https://libgen.is/anything")
    # Placeholder allows EVERYTHING — that's the contract.
    assert v.allowed is True


# ── Verdict shape ────────────────────────────────────────────────


def test_legal_gate_verdict_is_frozen():
    v = LegalGateVerdict(allowed=True, reason=None, gate_kind="sql_where_registry")
    with pytest.raises(Exception):
        # FrozenInstanceError is a subclass of AttributeError; either is fine.
        v.allowed = False  # type: ignore[misc]


# ── Personal-Reading Lane (SPR-02) — the go-live gate refuses a planted
#    third-party-on-servable violation. ───────────────────────────────
#
# DELIBERATE ARCHITECTURE NOTE (M6, intellectual honesty): the substrate.legal_gate
# module is a RETRIEVAL-TIME REGISTRY denylist (banned URLs / authors / titles /
# corpus-ids / content-hash prefixes). It does NOT call substrate.corpus_audit.run_audit
# and has no hardcoded check-name allowlist that could drop a new corpus check.
# The CORPUS-LEVEL go-live gate for the new third_party_servable check is
# run_audit (+ the corpus_audit CLI's non-zero exit), which the pre-merge / CI
# path and the corpus-mass-ingest runbook consult. So the "gate refuses a planted
# violation" assertion is asserted against run_audit here (the real consumer),
# and the registry legal-gate is verified to remain ORTHOGONAL — it neither
# filters nor swallows the new check, because it never inspects corpus checks at
# all. (The per-check non-vacuity of CHECK_THIRD_PARTY_SERVABLE itself lives in
# tests/test_corpus_audit.py; this is the gate-surface assertion M6 asks for.)


def test_corpus_audit_gate_refuses_planted_third_party_servable(tmp_path):
    """The corpus go-live gate (run_audit) refuses a corpus with a third-party
    web_article planted on a servable class without a basis: result.ok is False
    and the failing check name is 'third_party_servable'."""
    from runtime.db_lock import connect_write
    from substrate.corpus_audit import CHECK_THIRD_PARTY_SERVABLE, run_audit
    from substrate.graph.schema import init_database_at_path

    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="test-seed") as con:
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, author, source_tier,
                 document_type, raw_text, content_class)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "doc-gate-leak",
                "https://example.com/leak.html",
                "Leaked Essay",
                "An Author",
                4,
                "web_article",
                "A third-party essay body long enough to be real content. " * 6,
                "user_owned",  # servable, no basis -> the §9.0 leak
            ],
        )
    result = run_audit(db_path, include_binding=False)
    assert result.ok is False, "the gate must refuse a planted third-party-servable leak"
    failed = [c.name for c in result.failed_checks]
    assert CHECK_THIRD_PARTY_SERVABLE in failed
    assert CHECK_THIRD_PARTY_SERVABLE == "third_party_servable"


def test_registry_legal_gate_is_orthogonal_to_corpus_checks():
    """The registry legal-gate neither imports nor filters corpus_audit checks —
    it is a retrieval-time URL/author denylist, a different layer. This pins the
    M6 finding that there is no hardcoded check allowlist dropping the new check."""
    import inspect

    import substrate.legal_gate as lg
    import substrate.legal_gate.gate as lg_gate

    for mod in (lg, lg_gate):
        src = inspect.getsource(mod)
        assert "run_audit" not in src, (
            f"{mod.__name__} unexpectedly calls run_audit — re-verify it does not "
            "filter corpus checks to a hardcoded subset"
        )
        assert "corpus_audit" not in src
