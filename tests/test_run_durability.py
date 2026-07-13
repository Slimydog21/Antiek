from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from substrate.run_durability import (
    Checkpoint,
    CheckpointKind,
    ConcurrentAppendError,
    EventKind,
    FailureDecision,
    FailureKind,
    FailurePolicy,
    FakeDurableRunner,
    FloorName,
    FloorObservation,
    InMemoryEventLogPort,
    TraceError,
    TraceEvent,
    append_cas,
    reconstruct,
)
from substrate.run_durability.trace import GENESIS_HASH, SCHEMA_VERSION

BRIEF = "a" * 64
OTHER_BRIEF = "b" * 64
NOW = datetime(2026, 7, 11, 3, 0, tzinfo=UTC)


def clock() -> datetime:
    return NOW


def runner(
    port: InMemoryEventLogPort, run_id: str = "run-1", brief: str = BRIEF
) -> FakeDurableRunner:
    return FakeDurableRunner(port, run_id=run_id, approved_brief_hash=brief, clock=clock)


def event(
    kind: EventKind,
    data: Mapping[str, object],
    *,
    sequence: int = 0,
    previous: str = GENESIS_HASH,
    run_id: str = "run-x",
    brief: str = BRIEF,
) -> TraceEvent:
    return TraceEvent.create(
        run_id=run_id,
        approved_brief_hash=brief,
        sequence=sequence,
        kind=kind,
        occurred_at=NOW,
        data=data,
        previous_hash=previous,
    )


CHECKPOINTS = tuple(
    Checkpoint(kind, {"state_ref": f"state:{kind.value}"}) for kind in CheckpointKind
)


def execute_script(active: FakeDurableRunner, checkpoints: Sequence[Checkpoint]) -> None:
    if active.view is None:
        active.start()
    done = set(active.view.checkpoint_refs if active.view else {})
    for checkpoint in checkpoints:
        if checkpoint.kind.value not in done:
            active.step(f"step:{checkpoint.kind.value}")
            active.source_fetched(f"source:{checkpoint.kind.value}")
            active.checkpoint(checkpoint)


@pytest.mark.parametrize("kill_after", list(CheckpointKind))
def test_kill_reopen_equivalence_at_every_checkpoint_boundary(kill_after: CheckpointKind) -> None:
    uninterrupted_port = InMemoryEventLogPort()
    uninterrupted = runner(uninterrupted_port)
    execute_script(uninterrupted, CHECKPOINTS)
    expected = uninterrupted.complete()

    port = InMemoryEventLogPort()
    first = runner(port)
    boundary = next(i for i, item in enumerate(CHECKPOINTS) if item.kind is kill_after) + 1
    execute_script(first, CHECKPOINTS[:boundary])
    first.fail(FailureKind.PROCESS_KILLED, attempt=0)
    del first
    reopened = runner(port)  # genuinely reconstructs solely from the injected port
    reopened.resume()
    execute_script(reopened, CHECKPOINTS)
    actual = reopened.complete()
    assert (
        actual.report_ref,
        actual.checkpoint_refs,
        actual.steps,
        actual.sources,
        actual.completed,
    ) == (
        expected.report_ref,
        expected.checkpoint_refs,
        expected.steps,
        expected.sources,
        expected.completed,
    )
    assert actual.failures == 1 and actual.resumes == 1


def test_versioned_schema_source_step_and_canonical_bytes_roundtrip() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    active.step("step:search")
    active.source_fetched("source:doi:1")
    rows = port.read("run-1")
    assert [row.kind for row in rows] == [
        EventKind.RUN_STARTED,
        EventKind.STEP_RECORDED,
        EventKind.SOURCE_FETCHED,
    ]
    assert all(row.schema_version == SCHEMA_VERSION for row in rows)
    for row in rows:
        assert TraceEvent.from_json(row.to_json()).to_json() == row.to_json()
        assert TraceEvent.from_mapping(row.to_mapping()).to_mapping() == row.to_mapping()
    assert rows[-1].data == {"source_ref": "source:doi:1"}  # refs, never source content


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.pop("run_id"),
        lambda row: row.__setitem__("extra", 1),
        lambda row: row.__setitem__("sequence", True),
        lambda row: row.__setitem__("schema_version", True),
        lambda row: row.__setitem__("schema_version", 2),
        lambda row: row.__setitem__("kind", "future_kind"),
        lambda row: row.__setitem__("occurred_at", "2026-07-11T03:00:00Z"),
    ],
)
def test_parser_rejects_missing_extra_coerced_version_and_noncanonical_time(mutation: Any) -> None:
    row = event(EventKind.RUN_STARTED, {}).to_mapping()
    mutation(row)
    with pytest.raises((TraceError, ValueError)):
        TraceEvent.from_mapping(row)


@pytest.mark.parametrize("bad", [b'{"x":NaN}', b'{"x":Infinity}', b' {"x":1}', b'{"x":1.0}'])
def test_json_parser_rejects_constants_and_noncanonical_bytes(bad: bytes) -> None:
    with pytest.raises(TraceError):
        TraceEvent.from_json(bad)


def test_nested_refs_are_deep_frozen_and_views_are_immutable() -> None:
    refs = {"plan_ref": "plan:1"}
    checkpoint = Checkpoint(CheckpointKind.PLAN_READY, refs)
    refs["plan_ref"] = "evil"
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    view = active.checkpoint(checkpoint)
    assert view.checkpoint_refs["plan_ready"]["plan_ref"] == "plan:1"
    assert isinstance(view.checkpoint_refs, MappingProxyType)
    with pytest.raises(TypeError):
        view.checkpoint_refs["plan_ready"]["plan_ref"] = "evil"


def test_ref_shape_count_and_aggregate_bounds_block_chunked_content_smuggling() -> None:
    with pytest.raises(ValueError, match="end in _ref"):
        Checkpoint(CheckpointKind.PLAN_READY, {"chunk": "encoded:payload"})
    with pytest.raises(ValueError, match="at most 8"):
        Checkpoint(
            CheckpointKind.PLAN_READY,
            {f"chunk_{index}_ref": f"blob:{index}" for index in range(9)},
        )
    with pytest.raises(ValueError, match="1024"):
        Checkpoint(
            CheckpointKind.PLAN_READY,
            {f"chunk_{index}_ref": "x" * 255 for index in range(5)},
        )


def test_json_duplicate_keys_and_clock_regression_are_rejected() -> None:
    started = event(EventKind.RUN_STARTED, {})
    duplicate = started.to_json().replace(b"{", b'{"run_id":"run-1",', 1)
    with pytest.raises(TraceError, match="duplicate"):
        TraceEvent.from_json(duplicate)

    regressed = TraceEvent.create(
        run_id="run-1",
        approved_brief_hash=BRIEF,
        sequence=1,
        kind=EventKind.STEP_RECORDED,
        occurred_at=NOW - timedelta(seconds=1),
        data={"step_ref": "step:old"},
        previous_hash=started.event_hash,
    )
    with pytest.raises(TraceError, match="monotonic"):
        reconstruct((started, regressed))


class ChangingMapping(Mapping[str, object]):
    def __init__(self) -> None:
        self.calls = 0

    def __getitem__(self, key: str) -> object:
        return 1

    def __iter__(self) -> Iterator[str]:
        return iter(("step_ref",))

    def __len__(self) -> int:
        return 1

    def items(self) -> Any:
        self.calls += 1
        return (("step_ref", "step:one" if self.calls == 1 else "step:two"),)


class SmugglingMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        return "step:one"

    def __iter__(self) -> Iterator[str]:
        return iter(("step_ref",))

    def __len__(self) -> int:
        return 1

    def items(self) -> Any:
        return (("step_ref", "step:one"), ("hidden", "payload"))


@pytest.mark.parametrize("hostile", [ChangingMapping(), SmugglingMapping()])
def test_hostile_custom_mapping_content_smuggling_is_rejected(
    hostile: Mapping[str, object],
) -> None:
    with pytest.raises(TraceError):
        event(EventKind.STEP_RECORDED, hostile)


@pytest.mark.parametrize("refs", [{1: "ref:1"}, {"x": 1}, {"x": "has space"}, {}])
def test_invalid_nested_refs_are_rejected(refs: dict[object, object]) -> None:
    with pytest.raises((TraceError, ValueError)):
        event(EventKind.CHECKPOINT_RECORDED, {"checkpoint_kind": "plan_ready", "refs": refs})


@pytest.mark.parametrize(
    "bad_clock",
    [
        lambda: datetime(2026, 1, 1),
        lambda: datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))),
        lambda: "not-a-date",
    ],
)
def test_unsafe_clocks_are_rejected(bad_clock: Any) -> None:
    policy = FailurePolicy(clock=bad_clock)
    with pytest.raises((TraceError, TypeError)):
        policy.decide(FailureKind.TIMEOUT, attempt=0)


@pytest.mark.parametrize("failure", list(FailureKind))
def test_failure_taxonomy_default_terminal_and_attempt_bound(failure: FailureKind) -> None:
    policy = FailurePolicy(clock=clock, max_transient_attempts=2)
    assert policy.decide(failure, attempt=2).decision is FailureDecision.TERMINAL
    assert policy.decide("future_unknown", attempt=0).decision is FailureDecision.TERMINAL
    with pytest.raises(ValueError):
        policy.decide(failure, attempt=True)


def test_transient_failure_records_retry_and_resumes_once() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    failed = active.fail(FailureKind.TIMEOUT, attempt=0)
    assert failed.failures == 1 and failed.unresolved_resumable_sequence == 1
    resumed = active.resume()
    assert resumed.resumes == 1 and resumed.unresolved_resumable_sequence is None
    with pytest.raises(ValueError):
        active.resume()
    assert port.read("run-1")[1].data["retry_at"] == "2026-07-11T03:00:00.000000Z"


def test_durable_boundary_rejects_unknown_retry_and_reset_attempt_counter() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    with pytest.raises(TraceError, match="fail-closed"):
        active.prepare(
            EventKind.FAILURE_RECORDED,
            {
                "failure": "future_unknown",
                "attempt": 0,
                "attempt_limit": 3,
                "decision": "retry",
                "decided_at": "2026-07-11T03:00:00.000000Z",
                "retry_at": "2026-07-11T03:00:00.000000Z",
            },
        )

    active.fail(FailureKind.TIMEOUT, attempt=0)
    active.resume()
    with pytest.raises(TraceError, match="monotonically"):
        active.fail(FailureKind.TIMEOUT, attempt=0)


def test_retry_limit_is_small_and_cannot_be_inflated_by_a_forged_event() -> None:
    with pytest.raises(ValueError, match="between 1 and 3"):
        FailurePolicy(clock=clock, max_transient_attempts=4)
    with pytest.raises(TraceError, match="between 1 and 3"):
        event(
            EventKind.FAILURE_RECORDED,
            {
                "failure": "timeout",
                "attempt": 0,
                "attempt_limit": 999,
                "decision": "retry",
                "decided_at": "2026-07-11T03:00:00.000000Z",
                "retry_at": "2026-07-11T03:00:00.000000Z",
            },
        )


def test_retry_timing_cannot_precede_decision() -> None:
    with pytest.raises(TraceError, match="precede"):
        event(
            EventKind.FAILURE_RECORDED,
            {
                "failure": "timeout",
                "attempt": 0,
                "attempt_limit": 3,
                "decision": "retry",
                "decided_at": "2026-07-11T03:00:01.000000Z",
                "retry_at": "2026-07-11T03:00:00.000000Z",
            },
        )


def test_terminal_failure_never_resumes_or_accepts_following_events() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    view = active.fail(FailureKind.INTEGRITY_FAILURE, attempt=0)
    assert view.terminal_failure
    with pytest.raises((ValueError, TraceError)):
        active.resume()
    with pytest.raises(TraceError):
        active.complete()


def test_floor_resume_and_completion_requires_resolved_cause() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    active.trip_floor(FloorObservation(FloorName.CLAIM_SUPPORT, 0.4, 0.8, False))
    with pytest.raises(TraceError):
        active.complete()
    active.resume()
    assert active.complete().completed


def test_illegal_transitions_duplicate_backward_and_mismatched_resume_are_red() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    with pytest.raises(TraceError):
        active.checkpoint(CHECKPOINTS[0])
    active.start()
    with pytest.raises(TraceError):
        active.start()
    active.checkpoint(CHECKPOINTS[2])
    with pytest.raises(TraceError):
        active.checkpoint(CHECKPOINTS[1])
    active.trip_floor(FloorObservation(FloorName.SOURCE_DIVERSITY, 0, 1, False))
    forged = active.prepare(EventKind.RUN_RESUMED, {"from_sequence": 0})
    with pytest.raises(TraceError):
        active.append_prepared(forged)


def test_events_after_completion_are_rejected() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    active.complete()
    with pytest.raises(TraceError):
        active.step("step:late")


def test_two_stale_runners_prepare_same_head_second_cas_is_rejected() -> None:
    port = InMemoryEventLogPort()
    first = runner(port)
    first.start()
    left, right = runner(port), runner(port)
    a = left.prepare(EventKind.STEP_RECORDED, {"step_ref": "step:a"})
    b = right.prepare(EventKind.STEP_RECORDED, {"step_ref": "step:b"})
    left.append_prepared(a)
    with pytest.raises(ConcurrentAppendError):
        right.append_prepared(b)


class LyingPort(InMemoryEventLogPort):
    def append(self, event: TraceEvent, *, expected_sequence: int) -> None:
        pass


class WrongAppendPort(InMemoryEventLogPort):
    def append(self, event: TraceEvent, *, expected_sequence: int) -> None:
        wrong = TraceEvent.create(
            run_id=event.run_id,
            approved_brief_hash=event.approved_brief_hash,
            sequence=event.sequence,
            kind=EventKind.RUN_STARTED,
            occurred_at=NOW + timedelta(seconds=1),
            data={},
            previous_hash=event.previous_hash,
        )
        self._events.setdefault(event.run_id, []).append(wrong)


@pytest.mark.parametrize("port", [LyingPort(), WrongAppendPort()])
def test_cas_readback_rejects_false_success_or_different_append(port: InMemoryEventLogPort) -> None:
    with pytest.raises(ConcurrentAppendError):
        append_cas(port, event(EventKind.RUN_STARTED, {}))


def test_exact_brief_run_chain_and_tamper_anchors_are_red() -> None:
    port = InMemoryEventLogPort()
    active = runner(port)
    active.start()
    active.step("step:1")
    rows = list(port.read("run-1"))
    with pytest.raises(ValueError, match="different approved brief"):
        runner(port, brief=OTHER_BRIEF)
    variants = []
    for attr, value in [
        ("event_hash", "f" * 64),
        ("run_id", "other-run"),
        ("approved_brief_hash", OTHER_BRIEF),
        ("sequence", 4),
        ("previous_hash", "e" * 64),
    ]:
        clone = TraceEvent.from_json(rows[1].to_json())
        object.__setattr__(clone, attr, value)
        variants.append([rows[0], clone])
    for forged in variants:
        with pytest.raises((TraceError, ValueError)):
            reconstruct(forged)
    with pytest.raises(TraceError):
        reconstruct([rows[0], rows[0]])


def test_owned_seam_has_no_prohibited_imports_or_paths() -> None:
    root = Path("substrate/run_durability")
    forbidden_imports = {
        "pathlib",
        "sqlite3",
        "duckdb",
        "requests",
        "httpx",
        "socket",
        "subprocess",
        "orchestration",
        "runtime",
    }
    forbidden_words = {"midnight_oil", "reservation", "provider", "budget"}
    for path in root.glob("*.py"):
        source = path.read_text()
        tree = ast.parse(source)
        imported = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
        }
        assert imported.isdisjoint(forbidden_imports), (path, imported & forbidden_imports)
        assert forbidden_words.isdisjoint(source.lower().split()), path
    assert not any(
        part in {"midnight_oil", "runtime", "orchestration"}
        for path in root.rglob("*")
        for part in path.parts
    )
