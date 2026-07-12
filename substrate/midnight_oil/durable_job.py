"""Durable detail, stage-control, and evidence checkpoints for Midnight Oil."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .budget_ledger import BudgetLedger, StageBudgetExposure
from .job import _job_from_row, _job_to_row
from .operation_queue import OperationQueue
from .stages import (
    StageEffectReceipt,
    StageFailureReason,
    StagePlan,
    StagePlanItem,
    StageReceipt,
    StageRejectionReceipt,
    dispatch_fence_sha256,
    stage_failure_receipt_id,
)


class DurableJobStore:
    """SQLite job projection plus stage receipts; DuckDB remains cent authority."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._budget_path = self.path.with_suffix(".budget.duckdb")
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_job_details ("
                "job_id TEXT PRIMARY KEY, row_json TEXT NOT NULL)"
            )
            # JSON models are authoritative. SQL identity columns exist only
            # for keyed lookup and are checked against decoded JSON on read.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_stage_plans ("
                "job_id TEXT PRIMARY KEY, plan_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_stage_receipts ("
                "job_id TEXT NOT NULL, stage_key TEXT NOT NULL, receipt_json TEXT NOT NULL, "
                "PRIMARY KEY(job_id, stage_key), "
                "FOREIGN KEY(job_id) REFERENCES midnight_oil_stage_plans(job_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_stage_effects ("
                "receipt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, stage_key TEXT NOT NULL, "
                "effect_json TEXT NOT NULL, evidence_json TEXT NOT NULL, "
                "UNIQUE(job_id, stage_key), FOREIGN KEY(job_id, stage_key) REFERENCES "
                "midnight_oil_stage_receipts(job_id, stage_key))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS midnight_oil_stage_rejections ("
                "receipt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, stage_key TEXT NOT NULL, "
                "rejection_json TEXT NOT NULL, UNIQUE(job_id, stage_key), "
                "FOREIGN KEY(job_id, stage_key) REFERENCES "
                "midnight_oil_stage_receipts(job_id, stage_key))"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def put_job(self, job: dict[str, Any]) -> None:
        canonical = _job_to_row(_job_from_row(dict(job)))
        encoded = _canonical(canonical)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO midnight_oil_job_details(job_id, row_json) VALUES (?, ?) "
                    "ON CONFLICT(job_id) DO UPDATE SET row_json = excluded.row_json",
                    (canonical["job_id"], encoded),
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        _bounded(job_id, "job_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT row_json FROM midnight_oil_job_details WHERE job_id = ?",
                (job_id.strip(),),
            ).fetchone()
            if row is None:
                return None
            job = _decode_job(str(row[0]), expected_job_id=job_id)
            effect_rows = connection.execute(
                "SELECT stage_key FROM midnight_oil_stage_effects WHERE job_id = ? ORDER BY rowid",
                (job_id,),
            ).fetchall()
            effects = [self._read_effect(connection, job_id, str(row[0]))[1] for row in effect_rows]
            rejection_rows = connection.execute(
                "SELECT stage_key FROM midnight_oil_stage_rejections "
                "WHERE job_id = ? ORDER BY rowid",
                (job_id,),
            ).fetchall()
            effect_keys = {str(item[0]) for item in effect_rows}
            rejection_keys = {str(item[0]) for item in rejection_rows}
            if effect_keys & rejection_keys:
                raise ValueError("stage cannot have both success and rejection receipts")
            for rejection_row in rejection_rows:
                self._read_rejection(connection, job_id, str(rejection_row[0]))
        by_key = {
            str(item.get("step_key")): item
            for item in job.get("step_evidence", ())
            if isinstance(item, dict) and item.get("step_key")
        }
        for evidence in effects:
            by_key[str(evidence["step_key"])] = evidence
        job["step_evidence"] = list(by_key.values())
        job["returned_step_keys"] = list(
            dict.fromkeys(
                [
                    *job.get("returned_step_keys", ()),
                    *(str(item["step_key"]) for item in by_key.values()),
                ]
            )
        )
        return _job_to_row(_job_from_row(job))

    def budget_db_path(self) -> str:
        return str(self._budget_path)

    def initialize_stage_plan(self, plan: StagePlan) -> tuple[StageReceipt, ...]:
        if not isinstance(plan, StagePlan):
            raise TypeError("stage plan must be a validated StagePlan")
        encoded_plan = plan.model_dump_json()
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                if (
                    connection.execute(
                        "SELECT 1 FROM midnight_oil_job_details WHERE job_id = ?", (plan.job_id,)
                    ).fetchone()
                    is None
                ):
                    raise KeyError(plan.job_id)
                existing = connection.execute(
                    "SELECT job_id, plan_json FROM midnight_oil_stage_plans WHERE job_id = ?",
                    (plan.job_id,),
                ).fetchone()
                if existing is not None:
                    durable = _decode_plan(str(existing[1]), expected_job_id=str(existing[0]))
                    if durable != plan:
                        raise ValueError("stage plan replay conflicts with durable plan")
                    receipts = self._list_stage_receipts(connection, plan.job_id)
                    self._assert_exact_roster(plan, receipts)
                    connection.execute("COMMIT")
                    return receipts
                connection.execute(
                    "INSERT INTO midnight_oil_stage_plans(job_id, plan_json) VALUES (?, ?)",
                    (plan.job_id, encoded_plan),
                )
                receipts = tuple(self._planned_receipt(plan, item) for item in plan.stages)
                connection.executemany(
                    "INSERT INTO midnight_oil_stage_receipts"
                    "(job_id, stage_key, receipt_json) VALUES (?, ?, ?)",
                    [
                        (plan.job_id, receipt.stage_key, receipt.model_dump_json())
                        for receipt in receipts
                    ],
                )
                connection.execute("COMMIT")
                return receipts
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def get_stage(self, job_id: str, stage_key: str) -> StageReceipt | None:
        _bounded(job_id, "job_id")
        _hash(stage_key, "stage_key")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_id, stage_key, receipt_json FROM midnight_oil_stage_receipts "
                "WHERE job_id = ? AND stage_key = ?",
                (job_id, stage_key),
            ).fetchone()
        return None if row is None else _decode_receipt(tuple(row))

    def list_stages(self, job_id: str) -> tuple[StageReceipt, ...]:
        _bounded(job_id, "job_id")
        with self._connect() as connection:
            return self._list_stage_receipts(connection, job_id)

    def get_stage_effect(
        self, job_id: str, stage_key: str
    ) -> tuple[StageEffectReceipt, dict[str, Any]] | None:
        """Return the immutable effect/evidence checkpoint for recovery."""
        _bounded(job_id, "job_id")
        _hash(stage_key, "stage_key")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM midnight_oil_stage_effects WHERE job_id = ? AND stage_key = ?",
                (job_id, stage_key),
            ).fetchone()
            if row is None:
                return None
            return self._read_effect(connection, job_id, stage_key)

    def get_stage_rejection(self, job_id: str, stage_key: str) -> StageRejectionReceipt | None:
        _bounded(job_id, "job_id")
        _hash(stage_key, "stage_key")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM midnight_oil_stage_rejections WHERE job_id = ? AND stage_key = ?",
                (job_id, stage_key),
            ).fetchone()
            if row is None:
                return None
            return self._read_rejection(connection, job_id, stage_key)

    def reserve_stage(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        input_evidence_sha256: str,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if (
            current.state == "reserved"
            and current.revision == expected_revision + 1
            and current.input_evidence_sha256 == input_evidence_sha256
            and current.lease_generation == lease_generation
        ):
            return current

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            return self._transition(
                job_id=job_id,
                stage_key=stage_key,
                expected_revision=expected_revision,
                expected_states=("planned",),
                mutate=lambda row: StageReceipt(
                    **{
                        **row.model_dump(),
                        "state": "reserved",
                        "revision": row.revision + 1,
                        "input_evidence_sha256": input_evidence_sha256,
                        "budget_hold_id": exposure.hold_id,
                        "lease_generation": lease_generation,
                        "dispatch_fence_sha256": dispatch_fence_sha256(
                            stage=row.stage_key, lease_generation=lease_generation
                        ),
                        "reserved_at_ms": now_ms,
                    }
                ),
                require_predecessors=True,
            )

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"open"}),
            mutation=mutate,
        )

    def mark_stage_unknown(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state == "unknown" and current.revision == expected_revision + 1:
            return current

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            return self._transition(
                job_id=job_id,
                stage_key=stage_key,
                expected_revision=expected_revision,
                expected_states=("reserved",),
                mutate=lambda row: StageReceipt(
                    **{
                        **row.model_dump(),
                        "state": "unknown",
                        "revision": row.revision + 1,
                        "unknown_at_ms": now_ms,
                    }
                ),
            )

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"unknown"}),
            mutation=mutate,
        )

    def mark_stage_not_dispatched(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
        reason: StageFailureReason,
    ) -> StageReceipt:
        """Checkpoint a provider call proven not dispatched after hold release."""
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state == "not_dispatched" and current.revision == expected_revision + 1:
            if current.failure_reason != reason:
                raise ValueError("not-dispatched replay conflicts with durable reason")
            return current

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            if exposure.confirmed_cents or exposure.open_cents or exposure.unknown_cents:
                raise ValueError("not-dispatched stage budget exposure is not empty")
            failure_id = stage_failure_receipt_id(
                stage_key=current.stage_key,
                budget_hold_id=exposure.hold_id,
                dispatch_fence=current.dispatch_fence_sha256 or "",
                reason=reason,
            )
            return self._transition(
                job_id=job_id,
                stage_key=stage_key,
                expected_revision=expected_revision,
                expected_states=("reserved",),
                mutate=lambda row: StageReceipt(
                    **{
                        **row.model_dump(),
                        "state": "not_dispatched",
                        "revision": row.revision + 1,
                        "failure_receipt_id": failure_id,
                        "failure_reason": reason,
                        "failed_at_ms": now_ms,
                    }
                ),
            )

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"released"}),
            mutation=mutate,
        )

    def checkpoint_stage_returned(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        effect: StageEffectReceipt,
        stage_evidence: dict[str, Any],
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        """Atomically persist stage-owned evidence and merge the job projection."""
        canonical_evidence = _canonical_stage_evidence(stage_evidence)
        evidence_sha, route_id, source_ids, event_id, actual_cents = _stage_evidence_binding(
            canonical_evidence, effect.provider_effect_key
        )
        if (
            effect.stage_key != stage_key
            or effect.output_sha256 != evidence_sha
            or effect.route_receipt_id != route_id
            or effect.source_receipt_ids != source_ids
            or effect.provider_event_id != event_id
            or effect.actual_cents != actual_cents
        ):
            raise ValueError("effect receipt conflicts with exact durable stage evidence")
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state in {"returned", "settled"}:
            with self._connect() as connection:
                persisted_effect, persisted_evidence = self._read_effect(
                    connection, job_id, stage_key
                )
            if (
                persisted_effect.receipt_id == effect.receipt_id
                and persisted_evidence == canonical_evidence
            ):
                return current
            raise ValueError("returned stage replay conflicts with durable effect")

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            with self._connect() as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    durable = self._read_stage(connection, job_id, stage_key)
                    if durable.state in {"returned", "settled"}:
                        persisted_effect, persisted_evidence = self._read_effect(
                            connection, job_id, stage_key
                        )
                        if (
                            persisted_effect.receipt_id == effect.receipt_id
                            and persisted_evidence == canonical_evidence
                        ):
                            connection.execute("COMMIT")
                            return durable
                        raise ValueError("returned stage replay conflicts with durable effect")
                    if durable.revision != expected_revision or durable.state not in {
                        "reserved",
                        "unknown",
                    }:
                        raise ValueError("stage changed before returned checkpoint")
                    if (
                        durable.provider_effect_key != effect.provider_effect_key
                        or item.kind != effect.kind
                    ):
                        raise ValueError("effect receipt conflicts with stage plan")
                    next_receipt = StageReceipt(
                        **{
                            **durable.model_dump(),
                            "state": "returned",
                            "revision": durable.revision + 1,
                            "unknown_at_ms": None,
                            "effect_receipt_id": effect.receipt_id,
                            "output_sha256": effect.output_sha256,
                            "returned_at_ms": effect.returned_at_ms,
                        }
                    )
                    encoded_effect = effect.model_dump_json()
                    encoded_evidence = _canonical(canonical_evidence)
                    connection.execute(
                        "INSERT INTO midnight_oil_stage_effects"
                        "(receipt_id, job_id, stage_key, effect_json, evidence_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            effect.receipt_id,
                            job_id,
                            stage_key,
                            encoded_effect,
                            encoded_evidence,
                        ),
                    )
                    self._merge_job_evidence(
                        connection, job_id, canonical_evidence, effect.provider_effect_key
                    )
                    self._write_stage(connection, durable, next_receipt)
                    connection.execute("COMMIT")
                    return next_receipt
                except sqlite3.IntegrityError as exc:
                    connection.execute("ROLLBACK")
                    raise ValueError(
                        "stage effect identity conflicts with durable evidence"
                    ) from exc
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"open", "unknown"}),
            mutation=mutate,
        )

    def checkpoint_stage_rejected(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        rejection: StageRejectionReceipt,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        """Persist a known-paid invalid response without merging user-facing evidence."""
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state in {"rejected", "rejected_settled"}:
            with self._connect() as connection:
                persisted = self._read_rejection(connection, job_id, stage_key)
            if persisted.receipt_id == rejection.receipt_id:
                return current
            raise ValueError("rejected stage replay conflicts with durable rejection")

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            with self._connect() as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    durable = self._read_stage(connection, job_id, stage_key)
                    if durable.revision != expected_revision or durable.state not in {
                        "reserved",
                        "unknown",
                    }:
                        raise ValueError("stage changed before rejection checkpoint")
                    if (
                        rejection.stage_key != stage_key
                        or rejection.provider_effect_key != durable.provider_effect_key
                        or rejection.kind != item.kind
                    ):
                        raise ValueError("rejection receipt conflicts with stage plan")
                    next_receipt = StageReceipt(
                        **{
                            **durable.model_dump(),
                            "state": "rejected",
                            "revision": durable.revision + 1,
                            "unknown_at_ms": None,
                            "rejection_receipt_id": rejection.receipt_id,
                            "raw_response_sha256": rejection.raw_response_sha256,
                            "returned_at_ms": rejection.returned_at_ms,
                        }
                    )
                    connection.execute(
                        "INSERT INTO midnight_oil_stage_rejections"
                        "(receipt_id, job_id, stage_key, rejection_json) VALUES (?, ?, ?, ?)",
                        (
                            rejection.receipt_id,
                            job_id,
                            stage_key,
                            rejection.model_dump_json(),
                        ),
                    )
                    self._write_stage(connection, durable, next_receipt)
                    connection.execute("COMMIT")
                    return next_receipt
                except sqlite3.IntegrityError as exc:
                    connection.execute("ROLLBACK")
                    raise ValueError("stage rejection identity conflicts") from exc
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"open", "unknown"}),
            mutation=mutate,
        )

    def mark_stage_rejection_settled(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state == "rejected_settled" and current.revision == expected_revision + 1:
            return current

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            with self._connect() as connection:
                rejection = self._read_rejection(connection, job_id, stage_key)
            if exposure.confirmed_cents != rejection.actual_cents:
                raise ValueError("settled budget actual cents conflict with stage rejection")
            return self._transition(
                job_id=job_id,
                stage_key=stage_key,
                expected_revision=expected_revision,
                expected_states=("rejected",),
                mutate=lambda row: StageReceipt(
                    **{
                        **row.model_dump(),
                        "state": "rejected_settled",
                        "revision": row.revision + 1,
                        "settled_at_ms": now_ms,
                    }
                ),
            )

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"settled"}),
            mutation=mutate,
        )

    def mark_stage_settled(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
    ) -> StageReceipt:
        current, plan, item = self._runtime_authority(job_id, stage_key)
        if current.state == "settled" and current.revision == expected_revision + 1:
            return current

        def mutate(exposure: StageBudgetExposure) -> StageReceipt:
            _same_hold(current, exposure)
            with self._connect() as connection:
                effect, _ = self._read_effect(connection, job_id, stage_key)
            if exposure.confirmed_cents != effect.actual_cents:
                raise ValueError("settled budget actual cents conflict with stage effect")
            return self._transition(
                job_id=job_id,
                stage_key=stage_key,
                expected_revision=expected_revision,
                expected_states=("returned",),
                mutate=lambda row: StageReceipt(
                    **{
                        **row.model_dump(),
                        "state": "settled",
                        "revision": row.revision + 1,
                        "settled_at_ms": now_ms,
                    }
                ),
            )

        return self._mutate_fenced(
            plan=plan,
            item=item,
            budget_ledger=budget_ledger,
            operation_queue=operation_queue,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_budget_states=frozenset({"settled"}),
            mutation=mutate,
        )

    def _runtime_authority(
        self, job_id: str, stage_key: str
    ) -> tuple[StageReceipt, StagePlan, StagePlanItem]:
        with self._connect() as connection:
            current = self._read_stage(connection, job_id, stage_key)
            plan = self._read_plan(connection, job_id)
            item = _item(plan, stage_key)
        if (
            current.operation_id != plan.operation_id
            or current.plan_hash != plan.plan_hash
            or current.ordinal != item.ordinal
            or current.provider_effect_key != item.provider_effect_key
        ):
            raise ValueError("stage receipt conflicts with durable plan")
        return current, plan, item

    @staticmethod
    def _mutate_fenced(
        *,
        plan: StagePlan,
        item: StagePlanItem,
        budget_ledger: BudgetLedger,
        operation_queue: OperationQueue,
        worker_id: str,
        lease_generation: int,
        now_ms: int,
        expected_budget_states: frozenset[str],
        mutation: Callable[[StageBudgetExposure], StageReceipt],
    ) -> StageReceipt:
        """Fence generation, then cent exposure, then the stage SQLite CAS."""

        def queue_action() -> tuple[StageReceipt, bool]:
            queued = operation_queue.get(plan.operation_id)
            if (
                queued is None
                or queued.job_id != plan.job_id
                or queued.next_step_index != item.ordinal
            ):
                raise ValueError("stage transition conflicts with queue cursor")
            return (
                budget_ledger.run_stage_fenced(
                    plan.job_id,
                    item.stage_key,
                    expected_states=expected_budget_states,
                    action=lambda exposure: mutation(_validate_exposure(exposure, item)),
                ),
                False,
            )

        return operation_queue.run_fenced(
            operation_id=plan.operation_id,
            worker_id=worker_id,
            lease_generation=lease_generation,
            now_ms=now_ms,
            expected_step_index=item.ordinal,
            action=queue_action,
        )

    def _transition(
        self,
        *,
        job_id: str,
        stage_key: str,
        expected_revision: int,
        expected_states: tuple[str, ...],
        mutate: Any,
        require_predecessors: bool = False,
        replay: Any = None,
    ) -> StageReceipt:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._read_stage(connection, job_id, stage_key)
                if replay is not None and replay(current):
                    connection.execute("COMMIT")
                    return current
                if current.revision != expected_revision or current.state not in expected_states:
                    raise ValueError("stage changed before transition")
                if require_predecessors:
                    item = _item(self._read_plan(connection, job_id), stage_key)
                    for predecessor in item.predecessor_stage_keys:
                        predecessor_receipt = self._read_stage(connection, job_id, predecessor)
                        if predecessor_receipt.state != "settled":
                            raise ValueError("stage predecessor is not settled")
                updated = mutate(current)
                if not isinstance(updated, StageReceipt):
                    raise TypeError("stage transition must produce StageReceipt")
                self._write_stage(connection, current, updated)
                connection.execute("COMMIT")
                return updated
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _write_stage(
        connection: sqlite3.Connection,
        current: StageReceipt,
        updated: StageReceipt,
    ) -> None:
        changed = connection.execute(
            "UPDATE midnight_oil_stage_receipts SET receipt_json = ? "
            "WHERE job_id = ? AND stage_key = ? AND receipt_json = ?",
            (
                updated.model_dump_json(),
                current.job_id,
                current.stage_key,
                current.model_dump_json(),
            ),
        )
        if changed.rowcount != 1:
            raise ValueError("stage transition lost compare-and-set")

    def _merge_job_evidence(
        self,
        connection: sqlite3.Connection,
        job_id: str,
        evidence: dict[str, Any],
        evidence_key: str,
    ) -> None:
        row = connection.execute(
            "SELECT row_json FROM midnight_oil_job_details WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError("stage job projection disappeared")
        job = _decode_job(str(row[0]), expected_job_id=job_id)
        merged = [
            item for item in job.get("step_evidence", ()) if item.get("step_key") != evidence_key
        ]
        merged.append(evidence)
        returned = list(dict.fromkeys([*job.get("returned_step_keys", ()), evidence_key]))
        job["step_evidence"] = merged
        job["returned_step_keys"] = returned
        canonical = _job_to_row(_job_from_row(job))
        connection.execute(
            "UPDATE midnight_oil_job_details SET row_json = ? WHERE job_id = ?",
            (_canonical(canonical), job_id),
        )

    def _read_plan(self, connection: sqlite3.Connection, job_id: str) -> StagePlan:
        row = connection.execute(
            "SELECT job_id, plan_json FROM midnight_oil_stage_plans WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _decode_plan(str(row[1]), expected_job_id=str(row[0]))

    def _read_stage(
        self, connection: sqlite3.Connection, job_id: str, stage_key: str
    ) -> StageReceipt:
        row = connection.execute(
            "SELECT job_id, stage_key, receipt_json FROM midnight_oil_stage_receipts "
            "WHERE job_id = ? AND stage_key = ?",
            (job_id, stage_key),
        ).fetchone()
        if row is None:
            raise KeyError(stage_key)
        return _decode_receipt(tuple(row))

    def _read_effect(
        self, connection: sqlite3.Connection, job_id: str, stage_key: str
    ) -> tuple[StageEffectReceipt, dict[str, Any]]:
        row = connection.execute(
            "SELECT receipt_id, job_id, stage_key, effect_json, evidence_json "
            "FROM midnight_oil_stage_effects WHERE job_id = ? AND stage_key = ?",
            (job_id, stage_key),
        ).fetchone()
        if row is None:
            raise ValueError("returned stage lacks durable evidence")
        effect = StageEffectReceipt.model_validate_json(str(row[3]))
        evidence = json.loads(str(row[4]))
        if (
            str(row[0]) != effect.receipt_id
            or str(row[1]) != job_id
            or str(row[2]) != stage_key
            or effect.stage_key != stage_key
            or not isinstance(evidence, dict)
        ):
            raise ValueError("stage effect SQL identity conflicts with durable JSON")
        canonical_evidence = _canonical_stage_evidence(evidence)
        evidence_sha, route_id, source_ids, event_id, actual_cents = _stage_evidence_binding(
            canonical_evidence, effect.provider_effect_key
        )
        if (
            effect.output_sha256 != evidence_sha
            or effect.route_receipt_id != route_id
            or effect.source_receipt_ids != source_ids
            or effect.provider_event_id != event_id
            or effect.actual_cents != actual_cents
        ):
            raise ValueError("durable stage evidence conflicts with its effect receipt")
        return effect, canonical_evidence

    def _read_rejection(
        self, connection: sqlite3.Connection, job_id: str, stage_key: str
    ) -> StageRejectionReceipt:
        row = connection.execute(
            "SELECT receipt_id, job_id, stage_key, rejection_json "
            "FROM midnight_oil_stage_rejections WHERE job_id = ? AND stage_key = ?",
            (job_id, stage_key),
        ).fetchone()
        if row is None:
            raise ValueError("rejected stage lacks durable rejection receipt")
        receipt = StageRejectionReceipt.model_validate_json(str(row[3]))
        if (
            str(row[0]) != receipt.receipt_id
            or str(row[1]) != job_id
            or str(row[2]) != stage_key
            or receipt.stage_key != stage_key
        ):
            raise ValueError("stage rejection SQL identity conflicts with durable JSON")
        return receipt

    def _list_stage_receipts(
        self, connection: sqlite3.Connection, job_id: str
    ) -> tuple[StageReceipt, ...]:
        rows = connection.execute(
            "SELECT job_id, stage_key, receipt_json FROM midnight_oil_stage_receipts "
            "WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        receipts = tuple(_decode_receipt(tuple(row)) for row in rows)
        return tuple(sorted(receipts, key=lambda receipt: receipt.ordinal))

    @staticmethod
    def _planned_receipt(plan: StagePlan, item: StagePlanItem) -> StageReceipt:
        return StageReceipt(
            operation_id=plan.operation_id,
            job_id=plan.job_id,
            plan_hash=plan.plan_hash,
            stage_key=item.stage_key,
            ordinal=item.ordinal,
            provider_effect_key=item.provider_effect_key,
            state="planned",
            revision=0,
        )

    @staticmethod
    def _assert_exact_roster(plan: StagePlan, receipts: tuple[StageReceipt, ...]) -> None:
        if len(receipts) != len(plan.stages) or any(
            receipt.job_id != plan.job_id
            or receipt.operation_id != plan.operation_id
            or receipt.stage_key != item.stage_key
            or receipt.ordinal != item.ordinal
            or receipt.provider_effect_key != item.provider_effect_key
            or receipt.plan_hash != plan.plan_hash
            for receipt, item in zip(receipts, plan.stages, strict=True)
        ):
            raise ValueError("durable stage roster conflicts with exact plan")


def _validate_exposure(exposure: StageBudgetExposure, item: StagePlanItem) -> StageBudgetExposure:
    if (
        exposure.call_key != item.stage_key
        or exposure.role != item.router_role
        or exposure.projected_cents != item.projected_max_cents
    ):
        raise ValueError("stage transition conflicts with authoritative budget exposure")
    return exposure


def _same_hold(receipt: StageReceipt, exposure: StageBudgetExposure) -> None:
    if receipt.budget_hold_id != exposure.hold_id:
        raise ValueError("stage receipt conflicts with its authoritative budget hold")


def _canonical_stage_evidence(value: dict[str, Any]) -> dict[str, Any]:
    row = _job_to_row(
        _job_from_row(
            {
                "job_id": "stage-evidence-validation",
                "goals": ["validation"],
                "duration_minutes": 1,
                "model_id": None,
                "recommended_price_ceiling_usd": 1.0,
                "status": "running",
                "step_evidence": [value],
            }
        )
    )["step_evidence"]
    if not isinstance(row, list) or len(row) != 1:
        raise ValueError("stage evidence is invalid")
    return dict(row[0])


def _stage_evidence_binding(
    evidence: dict[str, Any], provider_effect_key: str
) -> tuple[str, str, tuple[str, ...], str, int]:
    if evidence.get("step_key") != provider_effect_key:
        raise ValueError("stage evidence key conflicts with provider effect key")
    encoded = _canonical(evidence).encode()
    route = evidence.get("route_receipt")
    sources = evidence.get("source_receipts")
    if not isinstance(route, dict) or not isinstance(sources, list):
        raise ValueError("stage evidence lacks route or source receipts")
    route_id = str(route.get("route_receipt_id") or "").strip()
    event_id = str(route.get("event_id") or "").strip()
    actual_cents = route.get("actual_cents")
    source_ids = tuple(
        str(row.get("source_id") or "").strip() for row in sources if isinstance(row, dict)
    )
    if (
        not route_id
        or not event_id
        or type(actual_cents) is not int
        or actual_cents < 0
        or any(not value for value in source_ids)
    ):
        raise ValueError("stage evidence receipt identifiers are incomplete")
    return hashlib.sha256(encoded).hexdigest(), route_id, source_ids, event_id, actual_cents


def _decode_job(encoded: str, *, expected_job_id: str) -> dict[str, Any]:
    value = json.loads(encoded)
    if not isinstance(value, dict):
        raise ValueError("stored Midnight Oil job is invalid")
    canonical = _job_to_row(_job_from_row(value))
    if canonical["job_id"] != expected_job_id:
        raise ValueError("job SQL identity conflicts with durable JSON")
    return canonical


def _decode_plan(encoded: str, *, expected_job_id: str) -> StagePlan:
    plan = StagePlan.model_validate_json(encoded)
    if plan.job_id != expected_job_id:
        raise ValueError("stage plan SQL identity conflicts with durable JSON")
    return plan


def _decode_receipt(row: tuple[object, ...]) -> StageReceipt:
    job_id, stage_key, encoded = row
    receipt = StageReceipt.model_validate_json(str(encoded))
    if receipt.job_id != str(job_id) or receipt.stage_key != str(stage_key):
        raise ValueError("stage receipt SQL identity conflicts with durable JSON")
    return receipt


def _item(plan: StagePlan, stage_key: str) -> StagePlanItem:
    for item in plan.stages:
        if item.stage_key == stage_key:
            return item
    raise KeyError(stage_key)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bounded(value: str, field: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise ValueError(f"{field} must be bounded and non-empty")


def _hash(value: str, field: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{field} must be canonical sha256")


__all__ = ["DurableJobStore"]
