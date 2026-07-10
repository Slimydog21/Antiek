"""Residual (acx): suite rewrite rationale cites title-only Write seed failures."""

from __future__ import annotations

from substrate.antiek_bench import (
    InMemoryBenchStore,
    SuiteRegistry,
    default_core_suite,
    propose_suite_delta,
    register_suite,
)


def test_propose_suite_delta_rationale_title_only_write_seeds() -> None:
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    store = InMemoryBenchStore()
    events = [
        {
            "task_class": "book_qa",
            "outcome": "failed",
            "prompt_hint": "[marketplace_host] Title only host",
            "source": "marketplace_host",
            "has_body": False,
        },
        {
            "task_class": "synthesize",
            "outcome": "worked",
            "prompt_hint": "[research_progress_complete] Final body",
            "source": "research_progress_complete",
            "has_body": True,
        },
    ]
    prop = propose_suite_delta(events, store=store, registry=reg)
    assert prop.status == "proposed"
    assert len(prop.added_item_ids) >= 1
    assert "title-only Write seeds (has_body=false): 1" in prop.rationale
    assert "body honesty → suite rewrite" in prop.rationale
    # Residual (acy): structured count on SuiteProposal + to_dict.
    assert prop.title_only_write_seed_count == 1
    assert prop.to_dict()["title_only_write_seed_count"] == 1


def test_propose_suite_delta_noop_still_mentions_title_only_if_failed_without_hint() -> None:
    """Failed title-only without prompt still counts in rationale when added empty.

    Empty-hint failures still add items via default regress prompt; when all
    fail to add (duplicate), title_only still appears if failures present.
    """
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    store = InMemoryBenchStore()
    # Two identical failed title-only events: second item_id may collide after first.
    events = [
        {
            "task_class": "distill",
            "outcome": "failed",
            "prompt_hint": "same-hint-body-missing",
            "source": "marketplace_host",
            "has_body": False,
        },
        {
            "task_class": "distill",
            "outcome": "failed",
            "prompt_hint": "same-hint-body-missing",
            "source": "marketplace_host",
            "has_body": False,
        },
    ]
    prop = propose_suite_delta(events, store=store, registry=reg)
    assert "title-only Write seeds (has_body=false): 2" in prop.rationale
    assert prop.title_only_write_seed_count == 2
