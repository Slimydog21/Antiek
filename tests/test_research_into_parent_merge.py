"""Research→parent-asset merge — contract tests.

Pins the hard-to-vary honesty invariants for the 1:1 research→read back-merge
(operator ask #3c/d). The module is pure: it produces a review-ready DRAFT
enriched document; it never mutates the source parent HTML and never commits the
merge.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.research_artifact.merge_into_parent import (  # noqa: E402
    MERGE_AUTHORITY,
    MIN_PARENT_HTML_CHARS,
    ResearchIntoParentMergeError,
    merge_research_into_parent,
)
from substrate.research_artifact.schema import (  # noqa: E402
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)

PARENT = (
    "<!doctype html><html><head><title>Book</title></head>"
    '<body><h1>The Chapter</h1><p>Some reading content here.</p></body></html>'
)


def _instance(
    *,
    investigation_id: str = "inv-1",
    problem_question: str = "What did the highlight mean?",
    insights: list[str] | None = None,
    questions: list[str] | None = None,
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
    source_event_ids: list[str] | None = None,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=problem_question,
        insights=[
            ArtifactInsight(node_id=f"n-{i}", text=t) for i, t in enumerate(insights or [])
        ],
        open_questions=[
            ArtifactQuestion(node_id=f"q-{i}", text=t) for i, t in enumerate(questions or [])
        ],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
        source_event_ids=source_event_ids or [],
    )


# --- fail-closed validation ---


def test_empty_parent_asset_id_rejected() -> None:
    with pytest.raises(ResearchIntoParentMergeError, match="parent_asset_id"):
        merge_research_into_parent(
            parent_asset_id="  ", parent_html=PARENT, instance=_instance()
        )


def test_empty_instance_investigation_id_rejected() -> None:
    with pytest.raises(ResearchIntoParentMergeError, match="investigation_id"):
        merge_research_into_parent(
            parent_asset_id="asset-1",
            parent_html=PARENT,
            instance=_instance(investigation_id="  "),
        )


def test_short_parent_html_rejected() -> None:
    # Boundary is the documented floor; assert the actual constant, not magic.
    assert MIN_PARENT_HTML_CHARS > 0
    with pytest.raises(ResearchIntoParentMergeError, match="too short"):
        merge_research_into_parent(
            parent_asset_id="asset-1",
            parent_html="t" * (MIN_PARENT_HTML_CHARS - 1),
            instance=_instance(),
        )


# --- non-destructive: draft always, merge never executed ---


def test_always_draft_merge_never_executed() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(insights=["a finding"]),
        operator_ack=True,  # even WITH ack, the pure module does not commit
    )

    assert result.draft is True
    assert result.merge_executed is False
    assert result.authority == MERGE_AUTHORITY


def test_source_parent_html_not_mutated() -> None:
    original = PARENT
    merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=original,
        instance=_instance(insights=["a finding"]),
    )

    assert original == PARENT  # the caller's string is untouched


def test_operator_ack_does_not_flip_merge_executed() -> None:
    no_ack = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=_instance(), operator_ack=False
    )
    with_ack = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=_instance(), operator_ack=True
    )

    assert no_ack.merge_executed is False
    assert with_ack.merge_executed is False  # authority layer commits, not this module


# --- escaping boundary: trusted parent, untrusted findings ---


def test_parent_html_passed_through_verbatim() -> None:
    # The parent contains legit HTML structure (tags, attributes) that must be
    # PRESERVED — it is already-sanitized trusted content, not re-escaped.
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(insights=["honest finding"]),
    )

    assert '<h1>The Chapter</h1>' in result.enriched_html
    assert "<!doctype html>" in result.enriched_html
    assert "</body></html>" in result.enriched_html


def test_malicious_finding_escaped() -> None:
    malicious = "<script>alert(1)</script>"
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(insights=[malicious]),
    )

    assert "<script>alert(1)</script>" not in result.enriched_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.enriched_html


def test_malicious_synthesis_escaped() -> None:
    malicious = '<img src=x onerror="steal()">'
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(synthesis_excerpt=malicious),
    )

    assert 'onerror="steal()"' not in result.enriched_html
    assert "&lt;img src=x onerror=" in result.enriched_html


def test_malicious_problem_question_escaped() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(problem_question="<b>bold</b> question"),
    )

    assert "<b>bold</b>" not in result.enriched_html
    assert "&lt;b&gt;bold&lt;/b&gt;" in result.enriched_html


# --- provenance: real, attributed, never fabricated ---


def test_findings_attributed_to_source_investigation() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(
            investigation_id="inv-42",
            insights=["finding one"],
            questions=["question one"],
        ),
    )

    assert 'data-source-investigation="inv-42"' in result.enriched_html
    assert "inv-42" in result.enriched_html


def test_insight_source_document_used_in_attribution() -> None:
    body = ResearchArtifactBody(
        investigation_id="inv-1",
        problem_question="q",
        insights=[ArtifactInsight(node_id="n-0", text="finding", source_document_id="doc-99")],
    )
    result = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=body
    )

    assert 'data-source-document="doc-99"' in result.enriched_html


def test_provenance_footer_names_source_events() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(source_event_ids=["evt-1", "evt-2"]),
    )

    assert "evt-1" in result.enriched_html
    assert "evt-2" in result.enriched_html
    assert "source events:" in result.enriched_html


def test_no_source_events_honest_not_fabricated() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(source_event_ids=[]),
    )

    assert "(none recorded)" in result.enriched_html


# --- no content invented ---


def test_empty_instance_honest_placeholders() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(insights=[], questions=[]),
    )

    assert result.findings_woven == 0
    assert "No insights from this instance." in result.enriched_html
    assert "No open questions from this instance." in result.enriched_html
    assert "No synthesis from this instance." in result.enriched_html


def test_withheld_synthesis_renders_honest_guard() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(synthesis_withheld=True),
    )

    assert "Synthesis not available" in result.enriched_html
    assert result.synthesis_woven is False


def test_findings_count_counts_real_findings() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(
            insights=["insight-1", "insight-2"],
            questions=["question-1"],
            synthesis_excerpt="a synthesis",
        ),
    )

    assert result.findings_woven == 3  # 2 insights + 1 question
    assert result.synthesis_woven is True


def test_empty_text_findings_dropped_from_count() -> None:
    body = ResearchArtifactBody(
        investigation_id="inv-1",
        problem_question="q",
        insights=[
            ArtifactInsight(node_id="n-0", text="   "),
            ArtifactInsight(node_id="n-1", text="real"),
        ],
        open_questions=[
            ArtifactQuestion(node_id="q-0", text=""),
            ArtifactQuestion(node_id="q-1", text="real-q"),
        ],
    )
    result = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=body
    )

    assert result.findings_woven == 2  # one real insight + one real question


# --- idempotency ---


def test_idempotent_output_for_same_inputs() -> None:
    instance = _instance(insights=["a", "b"], questions=["c"], synthesis_excerpt="synth")
    one = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=instance
    )
    two = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=instance
    )

    assert one.draft_hash == two.draft_hash
    assert one.enriched_html == two.enriched_html


def test_different_instance_different_hash() -> None:
    a = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=_instance(investigation_id="inv-a")
    )
    b = merge_research_into_parent(
        parent_asset_id="asset-1", parent_html=PARENT, instance=_instance(investigation_id="inv-b")
    )

    assert a.draft_hash != b.draft_hash


# --- insertion mechanics ---


def test_findings_inserted_before_body_close() -> None:
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=PARENT,
        instance=_instance(insights=["a finding"]),
    )

    # The findings section appears before </body>, preserving document structure.
    idx_section = result.enriched_html.index('id="research-findings"')
    idx_body_close = result.enriched_html.rindex("</body>")
    assert idx_section < idx_body_close


def test_findings_appended_when_no_body_close() -> None:
    no_body = "<div><p>some content without body close</p></div>"
    result = merge_research_into_parent(
        parent_asset_id="asset-1",
        parent_html=no_body,
        instance=_instance(insights=["a finding"]),
    )

    assert 'id="research-findings"' in result.enriched_html
    assert result.enriched_html.startswith("<div>")
    assert result.enriched_html.rstrip().endswith("</section>")
