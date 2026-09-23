"""The legal-gate registry is seeded and the gate bites on it (SPR-07 task 1).

Before this seed ``substrate/legal_gate/registry.py`` declared an empty
``BANNED_DOMAINS`` and the only real piracy denylist lived in
``acquisition/doc_to_html/converter.py`` as ``BLOCKED_DOMAINS``, where the
legal gate could not see it. Now the registry owns the list and the converter
imports it, so these tests pin three things:

- the two names agree and the seed is at least the 17 hosts the spec counted;
- ``default_legal_gate()`` refuses a shadow-library URL BECAUSE of the
  registry: emptying the registry flips the same URL to allowed. That
  differential is the only thing that separates "the gate now bites" from
  "the plumbing always worked and this test cannot fail";
- a clean host is still allowed (negative control).
"""

from __future__ import annotations

import pytest

from acquisition.doc_to_html import BLOCKED_DOMAINS
from substrate.legal_gate import RegistryBackedLegalGate, default_legal_gate, registry

SPEC_MINIMUM_SEED = 17

SHADOW_LIBRARY_URLS = (
    "https://libgen.is/book/index.php?md5=deadbeef",
    "https://annas-archive.org/md5/abc",
    "https://z-lib.org/book/1",
    "https://mirror.libgen.rs/x",  # subdomain of a seeded host
)


@pytest.fixture
def real_gate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure neither escape hatch swaps the real gate for the placeholder."""
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", raising=False)
    monkeypatch.delenv("ANTIEK_LEGAL_GATE_DISABLED", raising=False)


def test_registry_seed_is_the_converter_blocklist() -> None:
    assert len(registry.BANNED_DOMAINS) >= SPEC_MINIMUM_SEED
    assert set(registry.BANNED_DOMAINS) == set(BLOCKED_DOMAINS)
    assert len(set(registry.BANNED_DOMAINS)) == len(registry.BANNED_DOMAINS), (
        "duplicate entries in BANNED_DOMAINS"
    )


def test_registry_seed_entries_are_host_only() -> None:
    """The audit lint (``substrate.legal_gate.audit._inconsistencies``) flags
    schemes and paths; pin the same shape here so a bad entry fails at the
    registry rather than only at the audit CLI."""
    for entry in registry.BANNED_DOMAINS:
        assert entry == entry.strip().lower(), entry
        assert "://" not in entry and "/" not in entry, entry
        assert "." in entry, entry


@pytest.mark.usefixtures("real_gate_env")
@pytest.mark.parametrize("url", SHADOW_LIBRARY_URLS)
def test_default_gate_refuses_shadow_library_url(url: str) -> None:
    verdict = default_legal_gate().check_url(url)
    assert verdict.allowed is False
    assert verdict.gate_kind == "sql_where_registry"
    assert verdict.reason is not None and "banned domain" in verdict.reason


@pytest.mark.usefixtures("real_gate_env")
def test_default_gate_still_allows_clean_host() -> None:
    verdict = default_legal_gate().check_url("https://arxiv.org/abs/2412.12345")
    assert verdict.allowed is True
    assert verdict.gate_kind == "sql_where_registry"


@pytest.mark.usefixtures("real_gate_env")
def test_refusal_is_caused_by_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Differential mutation proof. Seeded: refused. Registry emptied: the
    SAME url is allowed. If the seeded half refuses for any reason other
    than the registry, the mutated half stays refused and this fails."""
    url = "https://libgen.is/x"
    seeded = default_legal_gate().check_url(url).allowed
    monkeypatch.setattr(registry, "BANNED_DOMAINS", ())
    mutated = default_legal_gate().check_url(url).allowed
    assert (seeded, mutated) == (False, True)


def test_converter_blocklist_is_not_a_second_source_of_truth() -> None:
    """An injected gate built from the converter's name must refuse exactly
    what the registry refuses: they are the same data."""
    gate = RegistryBackedLegalGate(banned_domains=BLOCKED_DOMAINS)
    for host in registry.BANNED_DOMAINS:
        assert gate.check_url(f"https://{host}/x").allowed is False, host
