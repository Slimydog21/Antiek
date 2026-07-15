from __future__ import annotations

import pytest

from substrate.research_artifact.derived_citation_source import (
    DerivedCitationConflict,
    canonical_derived_sources_context,
)
from substrate.schemas import DerivedCitationSource


def _source(ordinal: int, text: str = "Exact passage") -> DerivedCitationSource:
    suffix = f"{ordinal:064x}"
    return DerivedCitationSource(
        derived_asset_id="ast_" + "a" * 32,
        revision_id="rev_" + "b" * 32,
        content_sha256="c" * 64,
        generation=3,
        citation_id="dchunk_" + suffix,
        chunk_ordinal=ordinal,
        chunk_text_sha256=suffix,
        excerpt=text,
    )


def test_canonical_context_preserves_operator_order() -> None:
    sources = (_source(4, "Later"), _source(1, "Earlier"))

    assert canonical_derived_sources_context(sources) == (
        "[Evidence 1 of 2]\nLater\n\n[Evidence 2 of 2]\nEarlier"
    )


@pytest.mark.parametrize("sources", [(), (_source(1),), tuple(_source(i) for i in range(7))])
def test_canonical_context_rejects_invalid_cardinality(
    sources: tuple[DerivedCitationSource, ...],
) -> None:
    with pytest.raises(DerivedCitationConflict):
        canonical_derived_sources_context(sources)


def test_canonical_context_rejects_duplicate_and_mixed_revision() -> None:
    first = _source(1)
    with pytest.raises(DerivedCitationConflict):
        canonical_derived_sources_context((first, first))
    mixed = first.model_copy(update={"revision_id": "rev_" + "d" * 32})
    with pytest.raises(DerivedCitationConflict):
        canonical_derived_sources_context((first, mixed))


def test_canonical_context_caps_utf8_bytes() -> None:
    with pytest.raises(DerivedCitationConflict):
        canonical_derived_sources_context(tuple(_source(i, "x" * 8192) for i in range(1, 6)))
