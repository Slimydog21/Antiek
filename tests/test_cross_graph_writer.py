"""Tests for substrate.cross_graph_writer — §13.2 discovered-rule propagation.

Includes the architectural-incapability test:
  test_skill_patch_dp_isolation — verify that User B's private content
  cannot reach the shared substrate through a propagated DiscoveredRule
  (the rule carries only evidence HASHES, never raw content).
"""

from __future__ import annotations

import hashlib

import pytest

from substrate.cross_graph_writer import (
    CrossGraphWriterQueue,
    DiscoveredRule,
    RulePropagationEventKind,
    drain_queue,
    enqueue_for_propagation,
    propose_rule,
)


def test_propose_rule_hashes_evidence():
    """The proposer's raw chunks become sha256 hashes; raw content
    never enters the DiscoveredRule."""
    raw_a = b"private quantum chunk A -- not for sharing"
    raw_b = b"private quantum chunk B -- also private"
    rule = propose_rule(
        proposer_user_id="u-1",
        rule_kind="source_tier_assignment",
        rule_payload="Lukin lab papers = Tier-1 for neutral atom physics",
        supporting_chunks=[raw_a, raw_b],
        strength_score=0.9,
    )
    # Every evidence entry is a 64-char hex string.
    assert len(rule.evidence) == 2
    for entry in rule.evidence:
        assert len(entry) == 64
        assert all(c in "0123456789abcdef" for c in entry)
    # Verify the hashes are correct.
    assert rule.evidence[0] == hashlib.sha256(raw_a).hexdigest()
    assert rule.evidence[1] == hashlib.sha256(raw_b).hexdigest()


def test_propose_rule_strength_clamped():
    rule = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="x", supporting_chunks=[b"a"],
        strength_score=1.5,
    )
    assert rule.strength_score == 1.0
    rule2 = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="x", supporting_chunks=[b"a"],
        strength_score=-0.5,
    )
    assert rule2.strength_score == 0.0


def test_enqueue_accepts_hash_only_evidence():
    queue = CrossGraphWriterQueue()
    rule = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="patch", supporting_chunks=[b"chunk"],
        strength_score=0.7,
    )
    event = enqueue_for_propagation(queue, rule)
    assert event.kind == RulePropagationEventKind.ENQUEUED
    assert len(queue.pending) == 1


def test_enqueue_refuses_non_hash_evidence():
    """Architectural-incapability test #1: a hand-crafted rule with
    raw content in the evidence field is refused at enqueue time.

    The substrate is structurally incapable of propagating the raw
    content — it never enters the writer queue."""
    queue = CrossGraphWriterQueue()
    bad_rule = DiscoveredRule(
        rule_id="rule-attack-1",
        proposer_user_id="u-attacker",
        rule_kind="skill_patch",
        rule_payload="legitimate-looking discovered rule",
        evidence=(
            "this is raw chunk content, not a hash — attacker tries to leak",
            "another non-hash entry",
        ),
        strength_score=0.9,
    )
    event = enqueue_for_propagation(queue, bad_rule)
    assert event.kind == RulePropagationEventKind.REFUSED_NON_HASH_EVIDENCE
    # The bad rule never enters the queue.
    assert len(queue.pending) == 0


def test_enqueue_refuses_partial_non_hash_evidence():
    """Even ONE non-hash entry refuses the rule. Substrate is
    structurally strict."""
    queue = CrossGraphWriterQueue()
    bad_rule = DiscoveredRule(
        rule_id="rule-partial-1",
        proposer_user_id="u-attacker",
        rule_kind="skill_patch",
        rule_payload="x",
        evidence=(
            hashlib.sha256(b"chunk").hexdigest(),  # legit hash
            "leaked raw content alongside",  # non-hash
        ),
        strength_score=0.5,
    )
    event = enqueue_for_propagation(queue, bad_rule)
    assert event.kind == RulePropagationEventKind.REFUSED_NON_HASH_EVIDENCE
    assert len(queue.pending) == 0


def test_drain_queue_dp_shuffles_strength():
    """Strength score is DP-shuffled before propagation. With ε=1.0
    the noise is significant; the test verifies the shuffling step
    fires (the propagated rule's strength is in {0.0, 1.0})."""
    queue = CrossGraphWriterQueue()
    rule = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="x", supporting_chunks=[b"chunk"],
        strength_score=0.8,
    )
    enqueue_for_propagation(queue, rule)

    written: list[DiscoveredRule] = []
    drain_queue(queue, writer=written.append, epsilon=1.0)
    assert len(written) == 1
    # Strength gets binarised by the randomised-response shuffler.
    assert written[0].strength_score in (0.0, 1.0)


def test_drain_queue_propagation_event_recorded():
    queue = CrossGraphWriterQueue()
    rule = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="x", supporting_chunks=[b"chunk"],
        strength_score=0.5,
    )
    enqueue_for_propagation(queue, rule)
    drain_queue(queue, writer=lambda r: None, epsilon=1.0)
    kinds = [e.kind for e in queue.events]
    assert RulePropagationEventKind.DP_SHUFFLED in kinds
    assert RulePropagationEventKind.PROPAGATED_TO_SHARED in kinds


def test_drain_queue_writer_failure_continues():
    queue = CrossGraphWriterQueue()
    rule_a = propose_rule(
        proposer_user_id="u-1", rule_kind="skill_patch",
        rule_payload="a", supporting_chunks=[b"a"], strength_score=0.5,
    )
    rule_b = propose_rule(
        proposer_user_id="u-2", rule_kind="skill_patch",
        rule_payload="b", supporting_chunks=[b"b"], strength_score=0.5,
    )
    enqueue_for_propagation(queue, rule_a)
    enqueue_for_propagation(queue, rule_b)

    written: list[str] = []

    def writer(rule: DiscoveredRule) -> None:
        if rule.rule_id == rule_a.rule_id:
            raise RuntimeError("first write fails")
        written.append(rule.rule_id)

    drain_queue(queue, writer=writer, epsilon=1.0)
    # The second rule still gets written.
    assert written == [rule_b.rule_id]
    kinds = [e.kind for e in queue.events]
    assert RulePropagationEventKind.WRITER_FAILED in kinds


def test_no_raw_content_in_any_propagated_rule():
    """Architectural-incapability test #2: across all written rules,
    no evidence field contains anything that isn't a 64-char hex
    hash. Substrate-level guarantee, not policy."""
    queue = CrossGraphWriterQueue()
    private_chunks = [
        b"User B's quantum entanglement notes -- private",
        b"User B's research investigation step #42 -- private",
        b"User B's voice-note transcription -- also private",
    ]
    rule = propose_rule(
        proposer_user_id="u-B",
        rule_kind="skill_patch",
        rule_payload="Discovered: tier-1 sources include Lukin lab",
        supporting_chunks=private_chunks,
        strength_score=0.85,
    )
    enqueue_for_propagation(queue, rule)
    written: list[DiscoveredRule] = []
    drain_queue(queue, writer=written.append, epsilon=1.0)
    assert len(written) == 1
    for entry in written[0].evidence:
        # Sub-test: each entry is a hash.
        assert len(entry) == 64
        # Sub-test: NO private content appears anywhere in the
        # propagated artefact.
        for chunk in private_chunks:
            # The propagated artefact must NOT contain the raw chunk
            # bytes anywhere (rule_payload + evidence + everything).
            propagated_repr = repr(written[0])
            assert chunk.decode("utf-8") not in propagated_repr
