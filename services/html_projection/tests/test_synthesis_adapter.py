"""SPR-05 M2: synthesis → doc-model adapter — fidelity + rights filter.

The rights leak is asserted on the SERIALIZED doc-model (the island carries
leaked text even where the visible HTML hides it), per the sprint's rigor #3.
"""

from __future__ import annotations

import json

import pytest

from services.html_projection.adapters.synthesis import (
    Claim,
    RightsRefusal,
    SourceRef,
    SynthesisExport,
    adapt_synthesis,
)
from services.html_projection.context import RenderContext
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from services.html_projection.renderer import render

SERVABLE = SourceRef(
    document_id="doc-pd",
    document_title="On Liberty",
    content_class="public_domain",
    ip_holder_id=None,
    locator="/read/doc-pd?chunk=c1",
    chunk_text="PUBLIC DOMAIN PASSAGE",
)
PERSONAL = SourceRef(
    document_id="doc-pr",
    document_title="A Paul Graham essay",
    content_class="personal_reading",
    ip_holder_id="pg",
    locator="/read/doc-pr?chunk=c2",
    chunk_text="SECRET THIRD PARTY TEXT",
)
RESTRICTED_DOC = SourceRef(
    document_id="doc-rx",
    document_title="A gated book",
    content_class="restricted_pending_opt_in",
    ip_holder_id="mit-press",
    locator="/read/doc-rx",
    chunk_text="GATED BOOK TEXT",
)


def _export(**kw) -> SynthesisExport:
    base = dict(
        synthesis_id="syn-1",
        target_question="Does X hold?",
        thesis_text="X holds under Y.",
        recommendation="proceed",
        attribution_manifest={"document_ip_holders": {"doc-rx": "mit-press"}},
    )
    base.update(kw)
    return SynthesisExport(**base)


def test_golden_chain_carries_title_and_ip_holder():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [SERVABLE]),
                                         Claim("Claim B", [RESTRICTED_DOC])]))
    blob = json.dumps(dm)
    assert "Claim A" in blob and "Claim B" in blob
    assert "On Liberty" in blob  # servable source title in the cite label
    assert "mit-press" in blob  # ip_holder surfaces even for a cite-only source


def test_servable_text_is_embedded():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [SERVABLE])]))
    assert "PUBLIC DOMAIN PASSAGE" in json.dumps(dm)


def test_personal_reading_is_cite_only_no_leak():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [PERSONAL])]))
    blob = json.dumps(dm)
    # The chunk text MUST be absent from the serialized doc-model (the island).
    assert "SECRET THIRD PARTY TEXT" not in blob
    # The cite-only pointer IS present (title + ip_holder), and it is marked.
    assert "A Paul Graham essay" in blob
    assert "pg" in blob
    assert "cite-only" in blob


def test_restricted_doc_is_cite_only_no_leak():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [RESTRICTED_DOC])]))
    assert "GATED BOOK TEXT" not in json.dumps(dm)


def test_null_and_unknown_content_class_default_to_cite_only():
    for cc in (None, "some_unrecognised_class"):
        src = SourceRef(
            document_id="d", document_title="T", content_class=cc,
            ip_holder_id=None, locator="/x", chunk_text="DENY-BY-DEFAULT TEXT",
        )
        dm = adapt_synthesis(_export(claims=[Claim("A", [src])]))
        assert "DENY-BY-DEFAULT TEXT" not in json.dumps(dm)


def test_synthesis_level_restriction_refuses():
    with pytest.raises(RightsRefusal):
        adapt_synthesis(_export(restricted=True, restriction_reason="owner withheld"))


def test_island_round_trips():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [SERVABLE, PERSONAL])]))
    assert extract_island(render(dm, RenderContext())) == dm


def test_rendered_artifact_is_gate_clean():
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [SERVABLE, PERSONAL])]))
    assert_script_free(render(dm, RenderContext()))


def test_rendered_html_also_hides_restricted_text():
    # Belt-and-braces: the visible HTML, not only the doc-model, omits it.
    dm = adapt_synthesis(_export(claims=[Claim("Claim A", [PERSONAL])]))
    assert "SECRET THIRD PARTY TEXT" not in render(dm, RenderContext())


def test_external_federated_source_is_resolved_but_cite_only() -> None:
    src = SourceRef(
        document_id=None,
        document_title="work-1",
        content_class=None,
        ip_holder_id=None,
        external_source_id="core:work-1",
        source_kind="core",
        rights_class="source_terms_governed_metadata",
        retrieved_at="2026-01-01T00:00:00+00:00",
        source_tier=5,
        chunk_text="WITHHELD SOURCE TEXT",
    )
    dm = adapt_synthesis(_export(claims=[Claim("Claim", [src])]))
    encoded = json.dumps(dm)
    assert dm["metadata"]["provenance"]["complete"] is True
    assert "core:work-1" in encoded
    assert "source_terms_governed_metadata" in encoded
    assert "WITHHELD SOURCE TEXT" not in encoded
    assert "cite-only" in encoded
