"""Dogfood-judgment -> bench usage-event adapter — pure contract tests.

Pins the hard-to-vary honesty invariants from the sprint brief (§4). The adapter
is the production-signal wire that closes the recursive benchmark loop: it turns
the operator's judged talk-to-book answers into ``{task, success}`` events for
``propose_next_week_weights``.

Each test maps to one falsifiable invariant. Nothing here invents events,
coerces verdicts, or attributes models that don't exist.

Note on §4.7 (round-trip): ``usage_learn.propose_next_week_weights`` lives on PR
#810, which is reviewed ACCEPT but NOT yet merged to ``origin/main``. So the live
round-trip is import-gated — it auto-activates the moment #810 lands, exercising
the REAL learner (no engine grades its own homework). Until then an always-on
shape-contract test proves the events are mechanically compatible with the
documented ``[{task, success}]`` wire format.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.bench_presentation.dogfood_adapter import (  # noqa: E402
    TALK_TO_BOOK_TASK,
    DogfoodAdapterError,
    UsageEvent,
    dogfood_judgments_to_usage_events,
)

# usage_learn (#810) is reviewed-ACCEPT but not on origin/main yet. Import-gate
# the live round-trip so it runs against the REAL learner the instant it lands.
try:  # pragma: no cover - branch depends on merge state
    # usage_learn.py is absent on origin/main (lives on reviewed-unmerged #810),
    # so mypy reports import-untyped today; the ignore drops once #810 lands.
    from substrate.bench_presentation.usage_learn import (  # type: ignore[import-untyped]
        propose_next_week_weights,
    )
except ImportError:  # pragma: no cover
    propose_next_week_weights = None

ROUND_TRIP_AVAILABLE = propose_next_week_weights is not None

OWNER = "owner-1"
MODEL = "antiek-gpt-test"


def _row(**overrides: object) -> dict[str, object]:
    """A minimal valid judged-answer row, overridable per-test."""
    base: dict[str, object] = {
        "owner_id": OWNER,
        "verdict": "good",
        "answer_id": "ans-1",
        "parent_event_id": "ans-1",
        "model": MODEL,
        "grounded": True,
    }
    base.update(overrides)
    return base


def _no_parent_row(owner_id: str) -> dict[str, object]:
    """A valid row with neither answer_id nor parent_event_id resolvable."""
    row = _row(owner_id=owner_id)
    row.pop("answer_id", None)
    row.pop("parent_event_id", None)
    return row


# --- invariant 1: empty -> incomplete, no invented events ---


def test_empty_rows_are_incomplete_with_no_invented_events() -> None:
    result = dogfood_judgments_to_usage_events([], owner_id=OWNER, week_id="2026-W28")

    assert result.events == []
    assert result.incomplete is True
    assert result.skipped_non_bool == 0
    assert result.skipped_no_model == 0
    assert result.skipped_no_parent == 0
    assert result.skipped_wrong_owner == 0
    assert "no valid events produced" in " ".join(result.notes)


# --- verdict -> success mapping (§2) ---


def test_good_verdict_maps_to_success_true() -> None:
    result = dogfood_judgments_to_usage_events([_row(verdict="good")], owner_id=OWNER)

    assert len(result.events) == 1
    assert result.events[0].success is True
    assert result.events[0].task == TALK_TO_BOOK_TASK
    assert result.incomplete is False


def test_bad_verdict_maps_to_success_false() -> None:
    result = dogfood_judgments_to_usage_events([_row(verdict="bad")], owner_id=OWNER)

    assert len(result.events) == 1
    assert result.events[0].success is False


# --- invariant 2: non-bool verdict -> skip + count, never coerce ---


@pytest.mark.parametrize(
    "verdict",
    ["maybe", "GOOD", "", 1, 0, True, None],  # only {"good","bad"} are valid
)
def test_non_bool_verdict_skipped_and_counted(verdict: object) -> None:
    result = dogfood_judgments_to_usage_events(
        [_row(verdict=verdict)], owner_id=OWNER
    )

    assert result.events == []
    assert result.incomplete is True
    assert result.skipped_non_bool == 1
    assert any("non-bool" in n for n in result.notes)


def test_missing_verdict_field_skipped_and_counted() -> None:
    row = _row()
    del row["verdict"]
    result = dogfood_judgments_to_usage_events([row], owner_id=OWNER)

    assert result.events == []
    assert result.skipped_non_bool == 1


# --- invariant 3: no resolvable parent -> skip + count ---


def test_no_resolvable_parent_skipped_and_counted() -> None:
    row = _row()
    del row["answer_id"]
    del row["parent_event_id"]
    result = dogfood_judgments_to_usage_events([row], owner_id=OWNER)

    assert result.events == []
    assert result.skipped_no_parent == 1
    assert any("no resolvable parent" in n for n in result.notes)


def test_parent_event_id_alone_resolves_parent() -> None:
    # answer_id missing but parent_event_id present -> parent IS resolvable.
    row = _row()
    del row["answer_id"]
    result = dogfood_judgments_to_usage_events([row], owner_id=OWNER)

    assert len(result.events) == 1
    assert result.skipped_no_parent == 0


# --- invariant 4: ungrounded / no-model answer -> skip + count ---


def test_ungrounded_answer_skipped_and_counted() -> None:
    result = dogfood_judgments_to_usage_events(
        [_row(grounded=False)], owner_id=OWNER
    )

    assert result.events == []
    assert result.skipped_no_model == 1
    assert any("ungrounded or no-model" in n for n in result.notes)


def test_no_model_skipped_and_counted() -> None:
    row = _row()
    del row["model"]
    result = dogfood_judgments_to_usage_events([row], owner_id=OWNER)

    assert result.events == []
    assert result.skipped_no_model == 1


def test_empty_string_model_skipped_and_counted() -> None:
    result = dogfood_judgments_to_usage_events(
        [_row(model="")], owner_id=OWNER
    )

    assert result.events == []
    assert result.skipped_no_model == 1


# --- invariant 5: cross-owner -> skip + count (owner-scoped learning) ---


def test_cross_owner_skipped_and_counted() -> None:
    result = dogfood_judgments_to_usage_events(
        [_row(owner_id="someone-else")], owner_id=OWNER
    )

    assert result.events == []
    assert result.skipped_wrong_owner == 1
    assert any("wrong owner" in n for n in result.notes)


def test_only_owners_own_judgments_feed_bench() -> None:
    rows = [
        _row(owner_id="someone-else", answer_id="a-foreign"),
        _row(owner_id=OWNER, answer_id="a-mine", verdict="bad"),
        _row(owner_id="someone-else-2", answer_id="a-foreign-2"),
    ]
    result = dogfood_judgments_to_usage_events(rows, owner_id=OWNER)

    assert len(result.events) == 1
    assert result.events[0].success is False
    assert result.skipped_wrong_owner == 2


# --- invariant 6: determinism / order preserved ---


def test_same_input_same_output_order() -> None:
    rows = [
        _row(answer_id="a-1", verdict="good"),
        _row(answer_id="a-2", verdict="bad"),
        _row(answer_id="a-3", verdict="good"),
    ]
    one = dogfood_judgments_to_usage_events(rows, owner_id=OWNER)
    two = dogfood_judgments_to_usage_events(rows, owner_id=OWNER)

    assert one == two
    # Order is preserved as-given (pure transform; the caller owns trajectory
    # read order). The adapter does not reorder by fields it does not own.
    assert [e.success for e in one.events] == [True, False, True]


# --- accounting + advisory authority + week passthrough ---


def test_mixed_batch_honest_accounting() -> None:
    rows = [
        _row(owner_id=OWNER, answer_id="ok-1", verdict="good"),
        _row(owner_id="foreign", answer_id="x-1", verdict="good"),  # wrong owner
        _row(owner_id=OWNER, answer_id="ok-2", verdict="maybe"),  # non-bool
        _row(owner_id=OWNER, answer_id="ok-3", verdict="good", grounded=False),  # ungrounded
        _no_parent_row(OWNER),  # no resolvable parent
        _row(owner_id=OWNER, answer_id="ok-4", verdict="bad"),  # valid
    ]
    result = dogfood_judgments_to_usage_events(rows, owner_id=OWNER, week_id="2026-W28")

    assert len(result.events) == 2
    assert [e.success for e in result.events] == [True, False]
    assert result.skipped_wrong_owner == 1
    assert result.skipped_non_bool == 1
    assert result.skipped_no_model == 1
    assert result.skipped_no_parent == 1
    assert result.incomplete is False
    # Every skip category is accounted for in notes.
    joined = " ".join(result.notes)
    assert "wrong owner" in joined
    assert "non-bool" in joined
    assert "ungrounded or no-model" in joined
    assert "no resolvable parent" in joined


def test_authority_is_advisory_and_week_passthrough() -> None:
    result = dogfood_judgments_to_usage_events(
        [_row()], owner_id=OWNER, week_id="2026-W29"
    )

    assert result.authority == "dogfood_adapter_advisory"
    assert result.week_id == "2026-W29"


def test_empty_owner_id_is_fail_closed() -> None:
    with pytest.raises(DogfoodAdapterError):
        dogfood_judgments_to_usage_events([_row()], owner_id="   ")


# --- §4.7: mechanical compatibility with usage_learn ---


def test_events_shape_contract_for_usage_learn() -> None:
    """Always-on: each emitted event is exactly {task: str, success: bool} —
    the wire format ``propose_next_week_weights`` consumes. Proves the
    integration is lossless at the contract boundary without importing a
    module that is not yet on main."""
    result = dogfood_judgments_to_usage_events(
        [_row(verdict="good"), _row(verdict="bad")], owner_id=OWNER
    )

    assert len(result.events) == 2
    for event in result.events:
        assert isinstance(event, UsageEvent)
        assert isinstance(event.task, str)
        assert isinstance(event.success, bool)  # real bool, never coerced


@pytest.mark.skipif(
    not ROUND_TRIP_AVAILABLE,
    reason="usage_learn (#810) not merged to origin/main yet; activates on merge",
)
def test_round_trip_weights_sum_to_one() -> None:
    """Live integration: adapter output -> propose_next_week_weights -> weights
    summing to exactly 1.0. Runs against the REAL learner the moment #810
    lands (no reimplementation, no self-grading)."""
    assert propose_next_week_weights is not None  # narrow for mypy
    rows = [_row(answer_id=f"a-{i}", verdict=v) for i, v in enumerate(["good", "bad", "good", "bad"])]
    result = dogfood_judgments_to_usage_events(rows, owner_id=OWNER)
    # Documented wire format is [{task, success}] dicts.
    wire = [{"task": e.task, "success": e.success} for e in result.events]

    weights = propose_next_week_weights(wire, prior_weights={})

    total = sum(weights.values())
    # Largest-remainder conservation to 1.0 (the learner's invariant).
    assert total == pytest.approx(1.0)
