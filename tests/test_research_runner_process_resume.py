from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from runtime.research_runner.durable_execution import (
    AuthorizedRun,
    DurableWorkSupervisor,
    EffectReceipt,
    WorkUnit,
    effect_key,
)
from runtime.research_runner.durable_worker import FileReceiptExecutor
from substrate.event_log.run_durability_port import RunDurabilityEventLogPort
from substrate.run_durability import Checkpoint, CheckpointKind, EventKind

BRIEF = "a" * 64


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.value += timedelta(microseconds=1)
        return self.value


class MemoryExecutor:
    def __init__(self) -> None:
        self.receipts: dict[str, EffectReceipt] = {}
        self.calls = 0

    def lookup(self, key: str) -> EffectReceipt | None:
        return self.receipts.get(key)

    def execute(self, unit: WorkUnit, *, idempotency_key: str) -> EffectReceipt:
        self.calls += 1
        receipt = EffectReceipt(idempotency_key, f"artifact:{unit.boundary.value}")
        self.receipts[idempotency_key] = receipt
        return receipt


def units(query: str = "query:one") -> tuple[WorkUnit, ...]:
    return (
        WorkUnit(CheckpointKind.SOURCES_READY, {"query_ref": query}),
        WorkUnit(CheckpointKind.NOTES_READY, {"sources_ref": "sources:one"}),
        WorkUnit(CheckpointKind.SYNTHESIS_READY, {"notes_ref": "notes:one"}),
        WorkUnit(CheckpointKind.REPORT_READY, {"synthesis_ref": "synthesis:one"}),
    )


def authorization(work: tuple[WorkUnit, ...]) -> AuthorizedRun:
    return AuthorizedRun(
        "run:one", BRIEF, "brief:one", "plan:one", DurableWorkSupervisor.work_plan_hash(work)
    )


def test_authorization_and_manifest_fail_before_effect(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="lowercase"):
        AuthorizedRun("run:one", "A" * 64, "brief:one", "plan:one", "b" * 64)
    approved = units()
    executor = MemoryExecutor()
    supervisor = DurableWorkSupervisor(
        RunDurabilityEventLogPort(tmp_path / "events"),
        executor,
        authorization(approved),
        clock=Clock(),
    )
    with pytest.raises(ValueError, match="authorized work plan"):
        supervisor.execute(units("query:different"))
    assert executor.calls == 0
    assert supervisor.runner.view is None


def test_durable_plan_fences_competing_manifest_before_effect(tmp_path: Path) -> None:
    first, second = units(), units("query:different")
    port = RunDurabilityEventLogPort(tmp_path / "events")
    winner = MemoryExecutor()
    report = DurableWorkSupervisor(port, winner, authorization(first), clock=Clock()).execute(first)
    loser = MemoryExecutor()
    with pytest.raises(Exception, match="different durable work plan"):
        # Different plan hashes alter effect identity but cannot silently reuse the run.
        DurableWorkSupervisor(port, loser, authorization(second), clock=Clock()).execute(second)
    assert loser.calls == 0
    assert report == "artifact:report_ready"


def test_completed_reopen_validates_manifest_and_reuses_exact_report(tmp_path: Path) -> None:
    work = units()
    executor = MemoryExecutor()
    port = RunDurabilityEventLogPort(tmp_path / "events")
    first = DurableWorkSupervisor(port, executor, authorization(work), clock=Clock())
    report = first.execute(work)
    calls = executor.calls
    reopened = DurableWorkSupervisor(port, executor, authorization(work), clock=Clock())
    assert reopened.execute(work) == report
    assert executor.calls == calls
    view = reopened.runner.view
    assert view is not None
    assert view.checkpoint_refs[CheckpointKind.REPORT_READY.value]["report_ref"] == report
    assert view.report_ref == report


def test_forged_incomplete_completion_is_read_only_and_rejected(tmp_path: Path) -> None:
    work = units()
    executor = MemoryExecutor()
    port = RunDurabilityEventLogPort(tmp_path / "events")
    supervisor = DurableWorkSupervisor(port, executor, authorization(work), clock=Clock())
    supervisor.runner.start()
    supervisor.runner.checkpoint(
        Checkpoint(CheckpointKind.BRIEF_APPROVED, {"brief_ref": "brief:one"})
    )
    supervisor.runner.checkpoint(
        Checkpoint(
            CheckpointKind.PLAN_READY,
            {
                "plan_ref": "plan:one",
                "work_plan_ref": f"sha256:{DurableWorkSupervisor.work_plan_hash(work)}",
            },
        )
    )
    forged = supervisor.runner.prepare(EventKind.RUN_COMPLETED, {"report_ref": "artifact:forged"})
    supervisor.runner.append_prepared(forged)
    reopened = DurableWorkSupervisor(port, executor, authorization(work), clock=Clock())
    with pytest.raises(RuntimeError, match="missing an expected effect step"):
        reopened.execute(work)
    assert executor.calls == 0


def test_active_checkpoint_without_exact_step_cannot_complete(tmp_path: Path) -> None:
    work = units()
    executor = MemoryExecutor()
    port = RunDurabilityEventLogPort(tmp_path / "events")
    supervisor = DurableWorkSupervisor(port, executor, authorization(work), clock=Clock())
    supervisor.runner.start()
    supervisor.runner.checkpoint(
        Checkpoint(CheckpointKind.BRIEF_APPROVED, {"brief_ref": "brief:one"})
    )
    supervisor.runner.checkpoint(
        Checkpoint(
            CheckpointKind.PLAN_READY,
            {
                "plan_ref": "plan:one",
                "work_plan_ref": f"sha256:{DurableWorkSupervisor.work_plan_hash(work)}",
            },
        )
    )
    first = work[0]
    key = effect_key(authorization(work), first)
    receipt = executor.execute(first, idempotency_key=key)
    supervisor.runner.checkpoint(Checkpoint(first.boundary, {"outcome_ref": receipt.outcome_ref}))
    with pytest.raises(RuntimeError, match="lacks its exact effect step"):
        supervisor.execute(work)
    assert executor.calls == 1


def test_real_process_kill_reopens_and_reconciles_receipt(tmp_path: Path) -> None:
    marker = tmp_path / "effect-published"
    command = [
        sys.executable,
        "-m",
        "runtime.research_runner.durable_worker",
        "--root",
        str(tmp_path),
        "--run-id",
        "run:process",
        "--approved-brief-hash",
        BRIEF,
        "--stop-marker",
        str(marker),
    ]
    child = subprocess.Popen(command, cwd=Path(__file__).parents[1])
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "worker did not publish a receipt before timeout"
    finally:
        if child.poll() is None:
            os.kill(child.pid, 9)
        child.wait(timeout=5)
    assert child.returncode == -9

    resumed = subprocess.run(
        [*command[:-2], "--recover"],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    report = resumed.stdout.strip()
    assert report.startswith("artifact:sha256:")
    receipts = tuple((tmp_path / "receipts").glob("*.json"))
    assert len(receipts) == 4
    events = RunDurabilityEventLogPort(tmp_path / "events").read("run:process")
    kinds = [event.kind for event in events]
    assert EventKind.FAILURE_RECORDED in kinds
    assert EventKind.RUN_RESUMED in kinds
    assert kinds[-1] is EventKind.RUN_COMPLETED
    assert events[-1].data["report_ref"] == report
    assert len([event for event in events if event.kind is EventKind.STEP_RECORDED]) == 4
    checkpoints = [
        event.data["checkpoint_kind"]
        for event in events
        if event.kind is EventKind.CHECKPOINT_RECORDED
    ]
    assert checkpoints == [kind.value for kind in CheckpointKind]
    report_checkpoint = next(
        event
        for event in events
        if event.kind is EventKind.CHECKPOINT_RECORDED
        and event.data["checkpoint_kind"] == CheckpointKind.REPORT_READY.value
    )
    assert report_checkpoint.data["refs"]["report_ref"] == report

    baseline_root = tmp_path / "baseline"
    baseline = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.research_runner.durable_worker",
            "--root",
            str(baseline_root),
            "--run-id",
            "run:process",
            "--approved-brief-hash",
            BRIEF,
        ],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert baseline.stdout.strip() == report
    killed_receipts = {
        path.name: path.read_bytes() for path in (tmp_path / "receipts").glob("*.json")
    }
    baseline_receipts = {
        path.name: path.read_bytes() for path in (baseline_root / "receipts").glob("*.json")
    }
    assert baseline_receipts == killed_receipts


def test_recovery_refuses_non_process_resumable_edge(tmp_path: Path) -> None:
    work = units()
    port = RunDurabilityEventLogPort(tmp_path / "events")
    supervisor = DurableWorkSupervisor(port, MemoryExecutor(), authorization(work), clock=Clock())
    supervisor.runner.start()
    supervisor.runner.fail("rate_limited", attempt=0)
    with pytest.raises(RuntimeError, match="only its own process_killed"):
        supervisor.recover_interrupted()


def test_receipt_alias_recovery_canonical_bytes_and_root_pinning(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    executor = FileReceiptExecutor(root)
    unit = units()[0]
    key = "b" * 64
    receipt = executor.execute(unit, idempotency_key=key)
    final = root / f"{key}.json"
    alias = root / ".receipt-tmp-recovery"
    os.link(final, alias)
    assert executor.lookup(key) == receipt
    assert not alias.exists()

    final.write_text(
        json.dumps(
            {"outcome_ref": receipt.outcome_ref, "idempotency_key": key},
            indent=2,
        )
    )
    with pytest.raises(RuntimeError, match="canonical JSON"):
        executor.lookup(key)

    moved = tmp_path / "receipts-old"
    root.rename(moved)
    root.mkdir(mode=0o700)
    with pytest.raises(RuntimeError, match="changed after executor initialization"):
        executor.lookup(key)


def test_receipt_root_mode_mutation_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    executor = FileReceiptExecutor(root)
    root.chmod(0o755)
    with pytest.raises(RuntimeError, match="changed after executor initialization"):
        executor.lookup("c" * 64)


def test_live_root_replacement_cannot_redirect_publication(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    moved = tmp_path / "receipts-original"

    class ReplacingExecutor(FileReceiptExecutor):
        replaced = False

        def _open_root_fd(self) -> int:
            directory_fd = super()._open_root_fd()
            if not self.replaced:
                root.rename(moved)
                root.mkdir(mode=0o700)
                self.replaced = True
            return directory_fd

    executor = ReplacingExecutor(root)
    key = "d" * 64
    receipt = executor.execute(units()[0], idempotency_key=key)
    assert not tuple(root.glob("*.json"))
    original = moved / f"{key}.json"
    assert original.exists()
    assert receipt.idempotency_key == key
    with pytest.raises(RuntimeError, match="changed after executor initialization"):
        executor.lookup(key)
