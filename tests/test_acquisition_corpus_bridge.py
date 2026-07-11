from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from acquisition.corpus_bridge import (
    AcquisitionCorpusAdapter,
    from_arxiv_oai,
    from_openalex,
    from_substack,
)
from substrate.corpus_contract import CorpusContractError, CorpusDocument, CorpusMiss
from substrate.corpus_contract.conformance import FixtureDoc, assert_corpus_conformance

STAMP = 1_767_225_600.0
STAMP_UTC = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def _oai(fixtures: tuple[FixtureDoc, ...]) -> AcquisitionCorpusAdapter:
    return from_arxiv_oai(
        tuple(
            {
                "id": fixture.id,
                "title": fixture.content,
                "datestamp": "2026-01-01",
                "fetched_at": STAMP,
                "source": "arxiv_oai_pmh",
            }
            for fixture in fixtures
        )
    )


def _openalex(fixtures: tuple[FixtureDoc, ...]) -> AcquisitionCorpusAdapter:
    return from_openalex(
        tuple(
            {
                "id": fixture.id,
                "title": fixture.content,
                "abstract_inverted_index": None,
                "fetched_at": STAMP,
            }
            for fixture in fixtures
        )
    )


def _substack(fixtures: tuple[FixtureDoc, ...]) -> AcquisitionCorpusAdapter:
    return from_substack(
        tuple(
            {
                "url": fixture.id,
                "title": f"Post {fixture.id}",
                "body_html": f"<article>{fixture.content}</article>",
                "accessible": True,
                "fetched_at": STAMP,
            }
            for fixture in fixtures
        )
    )


@pytest.mark.parametrize("factory", [_oai, _openalex, _substack])
def test_every_accessible_record_family_passes_mandatory_conformance(
    factory: Callable[[tuple[FixtureDoc, ...]], AcquisitionCorpusAdapter],
) -> None:
    assert_corpus_conformance(factory)


@pytest.mark.parametrize(
    ("factory", "record", "source", "rights"),
    [
        (
            from_arxiv_oai,
            {
                "id": "2401.00001",
                "title": "Recursive research systems",
                "datestamp": "2026-01-01",
                "source": "arxiv_oai_pmh",
                "fetched_at": STAMP,
            },
            "arxiv_oai_pmh",
            "source_terms_governed_metadata",
        ),
        (
            from_openalex,
            {"id": "W1", "title": "Research graph", "fetched_at": STAMP},
            "openalex",
            "source_terms_governed_metadata",
        ),
        (
            from_substack,
            {
                "url": "https://example.substack.com/p/research",
                "title": "Research",
                "body_html": "<p>Operator research notes</p>",
                "accessible": True,
                "fetched_at": STAMP,
            },
            "substack",
            "publisher_rights_unknown_accessible",
        ),
    ],
)
def test_fetch_preserves_source_rights_identity_and_acquisition_time(
    factory: Callable[[tuple[Mapping[str, object], ...]], AcquisitionCorpusAdapter],
    record: dict[str, object],
    source: str,
    rights: str,
) -> None:
    adapter = factory((record,))
    id = str(record.get("id") or record.get("paperId") or record.get("url"))
    result = adapter.fetch(id)
    assert type(result) is CorpusDocument
    assert result.provenance.source_kind == source
    assert result.provenance.origin_ref == id
    assert result.provenance.license_class == rights
    assert result.provenance.retrieved_at == STAMP_UTC


def test_substack_paywall_is_metadata_searchable_but_never_fetchable() -> None:
    adapter = from_substack(
        (
            {
                "url": "https://writer.substack.com/p/private-analysis",
                "title": "Private semiconductor analysis",
                "body_html": None,
                "accessible": False,
                "fetched_at": STAMP,
            },
        )
    )
    assert adapter.search("semiconductor")[0].id.endswith("private-analysis")
    result = adapter.fetch("https://writer.substack.com/p/private-analysis")
    assert type(result) is CorpusMiss
    assert result.reason == "content unavailable by source policy"


def test_substack_html_becomes_inert_research_text() -> None:
    adapter = from_substack(
        (
            {
                "url": "https://writer.substack.com/p/open",
                "title": "Open",
                "body_html": (
                    "<article><p>Useful &amp; cited</p><script>steal()</script>"
                    "<style>body{display:none}</style><template>hidden</template></article>"
                ),
                "accessible": True,
                "fetched_at": STAMP,
            },
        )
    )
    result = adapter.fetch("https://writer.substack.com/p/open")
    assert type(result) is CorpusDocument
    assert result.content == "Useful & cited"


@pytest.mark.parametrize(
    "body_html",
    ["<script>unclosed", "<script><style>x</script></style>", "</template>orphan"],
)
def test_substack_malformed_suppressed_content_fails_closed(body_html: str) -> None:
    with pytest.raises(CorpusContractError, match="malformed suppressed"):
        from_substack(
            (
                {
                    "url": "https://writer.substack.com/p/malformed",
                    "title": "Malformed",
                    "body_html": body_html,
                    "accessible": True,
                    "fetched_at": STAMP,
                },
            )
        )


def test_openalex_reconstructs_valid_inverted_abstract() -> None:
    adapter = from_openalex(
        (
            {
                "id": "W2",
                "title": "Title",
                "abstract_inverted_index": {"knowledge": [0], "graph": [1, 3], "wins": [2]},
                "fetched_at": STAMP,
            },
        )
    )
    result = adapter.fetch("W2")
    assert type(result) is CorpusDocument
    assert result.content == "Title\n\nknowledge graph wins graph"


def test_input_mutation_cannot_change_snapshot() -> None:
    record: dict[str, object] = {"id": "W3", "title": "Original", "fetched_at": STAMP}
    adapter = from_openalex((record,))
    record["title"] = "Mutated secret"
    result = adapter.fetch("W3")
    assert type(result) is CorpusDocument
    assert result.content == "Original"
    assert adapter.search("Mutated") == ()


def test_duplicate_ids_fail_closed() -> None:
    record = {"id": "W4", "title": "Same", "fetched_at": STAMP}
    with pytest.raises(CorpusContractError, match="duplicate"):
        from_openalex((record, dict(record)))


def test_inaccessible_and_accessible_same_url_cannot_shadow_each_other() -> None:
    inaccessible = {
        "url": "https://writer.substack.com/p/changed",
        "title": "Changed",
        "body_html": None,
        "accessible": False,
        "fetched_at": STAMP,
    }
    accessible = {
        **inaccessible,
        "body_html": "<p>Now readable</p>",
        "accessible": True,
        "fetched_at": STAMP + 1,
    }
    with pytest.raises(CorpusContractError, match="duplicate"):
        from_substack((inaccessible, accessible))


def test_missing_paywall_body_field_fails_schema_boundary() -> None:
    with pytest.raises(CorpusContractError, match="body_html"):
        from_substack(
            (
                {
                    "url": "https://writer.substack.com/p/missing",
                    "title": "Missing",
                    "accessible": False,
                    "fetched_at": STAMP,
                },
            )
        )


def test_long_document_snippet_contains_late_query() -> None:
    adapter = from_openalex(
        (
            {
                "id": "W-late",
                "title": ("prefix " * 200) + "late-query" + (" suffix" * 200),
                "fetched_at": STAMP,
            },
        )
    )
    snippet = adapter.search("late-query")[0].snippet
    assert "late-query" in snippet
    assert len(snippet) <= 200


@pytest.mark.parametrize("fetched_at", [None, True, "now", float("nan"), float("inf")])
def test_hostile_acquisition_times_fail_closed(fetched_at: Any) -> None:
    with pytest.raises(CorpusContractError, match="fetched_at"):
        from_openalex(({"id": "W5", "title": "Time", "fetched_at": fetched_at},))


def test_malformed_abstract_and_access_state_fail_closed() -> None:
    with pytest.raises(CorpusContractError, match="position"):
        from_openalex(
            (
                {
                    "id": "W6",
                    "title": "Broken",
                    "abstract_inverted_index": {"collision": [0], "other": [0]},
                    "fetched_at": STAMP,
                },
            )
        )
    with pytest.raises(CorpusContractError, match="must not retain"):
        from_substack(
            (
                {
                    "url": "https://writer.substack.com/p/paywall",
                    "title": "Paywall",
                    "body_html": "leaked subscriber text",
                    "accessible": False,
                    "fetched_at": STAMP,
                },
            )
        )


def test_non_tuple_or_non_exact_dict_snapshot_rejected() -> None:
    with pytest.raises(CorpusContractError, match="exact tuple"):
        from_openalex([])  # type: ignore[arg-type]

    class MappingRecord(dict[str, object]):
        pass

    with pytest.raises(CorpusContractError, match="exact dict"):
        from_openalex((MappingRecord(id="W7", title="Subclass", fetched_at=STAMP),))
