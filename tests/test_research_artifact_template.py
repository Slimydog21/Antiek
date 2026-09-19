"""SPR-AHT-01 — ResearchArtifact template anti-fiction."""

from __future__ import annotations

from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


def test_empty_body_renders_honest_empty_state():
    body = ResearchArtifactBody(
        investigation_id="inv-empty",
        problem_question="What is unknown?",
    )
    html = render_html(body)
    assert "No insights in the graph yet" in html
    assert "No open questions in the graph yet" in html
    assert "No synthesis yet" in html
    assert 'id="antiek-artifact-v1"' in html
    assert "inv-empty" in html
    assert 'id="copy-json"' in html
    assert 'id="add-note"' in html


def test_content_hash_stable():
    body = ResearchArtifactBody(
        investigation_id="inv-1",
        problem_question="Q",
    )
    assert body.content_hash() == body.content_hash()


def test_claim_support_renders_distinct_direct_and_inherited_channels_escaped():
    body = ResearchArtifactBody(
        investigation_id="inv-claim-support",
        problem_question="Q",
        claim_support=[{
            "claim": "Claim <one>",
            "supporting_chunk_ids": ["chunk-<direct>"],
            "supporting_path_indices": [2],
            "inherited_support": [{
                "unit_id": "unit-<prior>",
                "qualification_state": "partial",
                "source_investigation_id": "prior-<leaf>",
                "supporting_leaf_investigation_id": "leaf-<current>",
            }],
        }],
    )
    html = render_html(body)
    assert 'id="claim-support"' in html
    assert "Claim &lt;one&gt;" in html
    assert "chunk-&lt;direct&gt;" in html
    assert "Reasoning paths:</strong> 2" in html
    assert "unit-&lt;prior&gt;" in html
    assert "prior-&lt;leaf&gt;" in html
    assert "leaf-&lt;current&gt;" in html
    assert '"qualification_state": "partial"' in html
    assert "Claim <one>" not in html


def test_partial_source_coverage_is_human_and_machine_visible():
    body = ResearchArtifactBody(
        investigation_id="inv-partial",
        problem_question="Q",
        source_coverage={
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": True,
            "partial_leaf_investigation_ids": ["leaf-1"],
            "sources": [
                {"source": source, "succeeded_leaves": succeeded, "total_leaves": 2}
                for source, succeeded in zip(
                    ("exa", "parallel", "arxiv", "substack"),
                    (2, 2, 1, 2),
                    strict=True,
                )
            ],
            "leaves": [
                {
                    "investigation_id": leaf,
                    "sources": [
                        {
                            "source": source,
                            "status": (
                                "failed" if leaf == "leaf-1" and source == "arxiv"
                                else "succeeded"
                            ),
                            "document_count": 1,
                        }
                        for source in ("exa", "parallel", "arxiv", "substack")
                    ],
                }
                for leaf in ("leaf-0", "leaf-1")
            ],
        },
    )
    html = render_html(body)

    assert 'id="source-coverage"' in html
    assert "Partial source coverage" in html
    assert "Do not interpret this artifact as comprehensive" in html
    assert "arxiv</strong>: 1/2 leaves succeeded" in html
    assert 'data-source="arxiv" data-status="failed"' in html
    assert '"partial_leaf_investigation_ids": [' in html


def test_inherited_reuse_is_separate_human_and_machine_provenance():
    body = ResearchArtifactBody(
        investigation_id="inv-inherited",
        problem_question="Q",
        inherited_reuse={
            "leaves": [
                {
                    "investigation_id": "leaf-<qualified>",
                    "state": "qualified",
                    "injected_unit_count": 1,
                    "qualifications": [{
                        "unit_id": "unit-<one>",
                        "source_investigation_id": "prior-1",
                        "state": "unknown",
                        "source_successes": [0, 0, 0, 0],
                        "total_leaves": 0,
                        "partial_leaf_count": 0,
                    }],
                },
                {
                    "investigation_id": "leaf-legacy",
                    "state": "legacy_unqualified",
                    "injected_unit_count": 2,
                    "qualifications": [],
                },
            ]
        },
    )
    html = render_html(body)

    assert 'id="inherited-reuse"' in html
    assert "Inherited knowledge is not direct evidence" in html
    assert "Legacy-unqualified" in html
    assert "leaf-&lt;qualified&gt;" in html
    assert "unit-&lt;one&gt;" in html
    assert '"inherited_reuse": {' in html
