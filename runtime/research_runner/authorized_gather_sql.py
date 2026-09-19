"""Durable DuckDB authority for SPR-DRL-16 gather receipts and exact budgets."""

from __future__ import annotations

import contextlib
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from runtime.db_lock import LockedConnection, connect_write
from runtime.research_runner.authorized_gather import (
    GatherAuthorityDenied,
    GatherCallClaim,
    GatherClaimState,
    GatherProviderResult,
)
from substrate.graph.schema import ANTIEK_GRAPH_SCHEMA_V17_AUTHORIZED_GATHER_SQL
from substrate.investigation_tenancy import InvestigationAuthority


def initialize_authorized_gather_schema(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError("authorized gather schema requires a LockedConnection")
    for statement in ANTIEK_GRAPH_SCHEMA_V17_AUTHORIZED_GATHER_SQL.strip().split(";"):
        if statement.strip():
            con.execute(statement)


def ensure_authorized_gather_schema(db_path: str) -> None:
    with connect_write(db_path, purpose="authorized_gather_schema") as con:
        initialize_authorized_gather_schema(con)


def _encode_result(result: GatherProviderResult) -> str:
    return json.dumps(
        {
            "document_ids": list(result.document_ids),
            "actual_cost_micros": result.actual_cost_micros,
            "tokens": result.tokens,
            "provider_receipt_id": result.provider_receipt_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_result(raw: str | None) -> GatherProviderResult | None:
    if raw is None:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "document_ids",
        "actual_cost_micros",
        "tokens",
        "provider_receipt_id",
    }:
        raise GatherAuthorityDenied("stored gather result is malformed")
    document_ids = value["document_ids"]
    if not isinstance(document_ids, list) or any(not isinstance(item, str) for item in document_ids):
        raise GatherAuthorityDenied("stored gather document IDs are malformed")
    return GatherProviderResult(
        tuple(document_ids),
        value["actual_cost_micros"],
        value["tokens"],
        value["provider_receipt_id"],
    )


class DuckDBAuthorizedGatherAuthority:
    """Authority-scoped durable implementation of receipt and exact-budget protocols."""

    def __init__(self, db_path: str, authority: InvestigationAuthority) -> None:
        self._db_path = db_path
        self._authority = authority

    @contextmanager
    def _transaction(self, purpose: str) -> Iterator[LockedConnection]:
        with connect_write(self._db_path, purpose=purpose) as con:
            con.execute("BEGIN TRANSACTION")
            try:
                yield con
            except BaseException:
                with contextlib.suppress(Exception):
                    con.execute("ROLLBACK")
                raise
            else:
                con.execute("COMMIT")

    @property
    def _scope(self) -> tuple[str, str]:
        return self._authority.account_digest, self._authority.investigation_digest

    def bind_plan(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        aggregate_max_cost_micros: int,
        aggregate_max_results: int,
    ) -> None:
        if investigation_id != self._authority.investigation_id:
            raise GatherAuthorityDenied("budget investigation authority drifted")
        with self._transaction("authorized_gather_bind_plan") as con:
            row = con.execute(
                "SELECT aggregate_max_cost_micros, aggregate_max_results "
                "FROM authorized_gather_plans WHERE account_digest = ? "
                "AND investigation_digest = ? AND plan_fingerprint = ?",
                [*self._scope, plan_fingerprint],
            ).fetchone()
            expected = (aggregate_max_cost_micros, aggregate_max_results)
            if row is not None:
                if tuple(row) != expected:
                    raise GatherAuthorityDenied("durable gather plan budget binding conflict")
                return
            con.execute(
                "INSERT INTO authorized_gather_plans "
                "(account_digest, investigation_digest, plan_fingerprint, "
                "aggregate_max_cost_micros, aggregate_max_results) VALUES (?, ?, ?, ?, ?)",
                [*self._scope, plan_fingerprint, *expected],
            )

    def reserve_micros(
        self,
        *,
        plan_fingerprint: str,
        investigation_id: str,
        projected_cost_micros: int,
        projected_results: int,
    ) -> str:
        if investigation_id != self._authority.investigation_id:
            raise GatherAuthorityDenied("reservation investigation authority drifted")
        if min(projected_cost_micros, projected_results) < 0:
            raise ValueError("projected gather usage must be non-negative")
        reservation_id = f"gather-reservation-{secrets.token_hex(16)}"
        with self._transaction("authorized_gather_reserve") as con:
            max_cost, max_results, spent, settled, held_cost, held_results = (
                self._reconciled_plan(con, plan_fingerprint)
            )
            if spent + held_cost + projected_cost_micros > max_cost:
                raise GatherAuthorityDenied("reviewed aggregate gather cost budget exceeded")
            if settled + held_results + projected_results > max_results:
                raise GatherAuthorityDenied("reviewed aggregate gather result budget exceeded")
            con.execute(
                "INSERT INTO authorized_gather_reservations "
                "(account_digest, investigation_digest, reservation_id, plan_fingerprint, "
                "projected_cost_micros, projected_results, state) "
                "VALUES (?, ?, ?, ?, ?, ?, 'held')",
                [
                    *self._scope,
                    reservation_id,
                    plan_fingerprint,
                    projected_cost_micros,
                    projected_results,
                ],
            )
            changed = con.execute(
                "UPDATE authorized_gather_plans SET held_cost_micros = held_cost_micros + ?, "
                "held_results = held_results + ? WHERE account_digest = ? "
                "AND investigation_digest = ? AND plan_fingerprint = ? RETURNING plan_fingerprint",
                [projected_cost_micros, projected_results, *self._scope, plan_fingerprint],
            ).fetchone()
            if changed != (plan_fingerprint,):
                raise GatherAuthorityDenied("gather reservation lost its plan")
        return reservation_id

    def _reconciled_plan(
        self, con: LockedConnection, plan_fingerprint: str
    ) -> tuple[int, int, int, int, int, int]:
        row = con.execute(
                "SELECT aggregate_max_cost_micros, aggregate_max_results, "
                "spent_cost_micros, settled_results, held_cost_micros, held_results "
                "FROM authorized_gather_plans WHERE account_digest = ? "
                "AND investigation_digest = ? AND plan_fingerprint = ?",
                [*self._scope, plan_fingerprint],
        ).fetchone()
        if row is None:
            raise GatherAuthorityDenied("gather plan budget is not bound")
        values = tuple(map(int, row))
        if min(values) < 0:
            raise GatherAuthorityDenied("stored gather plan budget is corrupt")
        sums = con.execute(
            "SELECT "
            "coalesce(sum(CASE WHEN state = 'settled' THEN actual_cost_micros ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN state = 'settled' THEN actual_results ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN state = 'held' THEN projected_cost_micros ELSE 0 END), 0), "
            "coalesce(sum(CASE WHEN state = 'held' THEN projected_results ELSE 0 END), 0) "
            "FROM authorized_gather_reservations WHERE account_digest = ? "
            "AND investigation_digest = ? AND plan_fingerprint = ?",
            [*self._scope, plan_fingerprint],
        ).fetchone()
        authoritative = tuple(map(int, sums))
        if values[2:] != authoritative:
            raise GatherAuthorityDenied("stored gather plan counters fail conservation")
        return values  # type: ignore[return-value]

    def _load_held(self, con: LockedConnection, reservation_id: str) -> tuple[Any, ...]:
        row = con.execute(
            "SELECT plan_fingerprint, projected_cost_micros, projected_results, state "
            "FROM authorized_gather_reservations WHERE account_digest = ? "
            "AND investigation_digest = ? AND reservation_id = ?",
            [*self._scope, reservation_id],
        ).fetchone()
        if row is None or row[3] != "held":
            raise GatherAuthorityDenied("gather reservation is missing or terminal")
        if int(row[1]) < 0 or int(row[2]) < 0:
            raise GatherAuthorityDenied("stored gather reservation is corrupt")
        return tuple(row)

    def release_micros(self, reservation_id: str) -> None:
        with self._transaction("authorized_gather_release") as con:
            plan_fingerprint, cost, results, _ = self._load_held(con, reservation_id)
            plan = self._reconciled_plan(con, plan_fingerprint)
            if plan[4] < cost or plan[5] < results:
                raise GatherAuthorityDenied("gather release would underflow plan holds")
            changed_reservation = con.execute(
                "UPDATE authorized_gather_reservations SET state = 'released' "
                "WHERE account_digest = ? AND investigation_digest = ? "
                "AND reservation_id = ? AND state = 'held' RETURNING reservation_id",
                [*self._scope, reservation_id],
            ).fetchone()
            changed_plan = con.execute(
                "UPDATE authorized_gather_plans SET held_cost_micros = held_cost_micros - ?, "
                "held_results = held_results - ? WHERE account_digest = ? "
                "AND investigation_digest = ? AND plan_fingerprint = ? RETURNING plan_fingerprint",
                [cost, results, *self._scope, plan_fingerprint],
            ).fetchone()
            if changed_reservation != (reservation_id,) or changed_plan != (plan_fingerprint,):
                raise GatherAuthorityDenied("gather release lost reservation conservation")

    def settle_micros(
        self,
        reservation_id: str,
        *,
        actual_cost_micros: int,
        actual_results: int,
        tokens: int,
    ) -> None:
        if min(actual_cost_micros, actual_results, tokens) < 0:
            raise ValueError("actual gather usage must be non-negative")
        with self._transaction("authorized_gather_settle") as con:
            plan_fingerprint, projected_cost, projected_results, _ = self._load_held(
                con, reservation_id
            )
            plan = self._reconciled_plan(con, plan_fingerprint)
            if plan[4] < projected_cost or plan[5] < projected_results:
                raise GatherAuthorityDenied("gather settlement would underflow plan holds")
            changed_reservation = con.execute(
                "UPDATE authorized_gather_reservations SET state = 'settled', "
                "actual_cost_micros = ?, actual_results = ?, tokens = ? "
                "WHERE account_digest = ? AND investigation_digest = ? "
                "AND reservation_id = ? AND state = 'held' RETURNING reservation_id",
                [actual_cost_micros, actual_results, tokens, *self._scope, reservation_id],
            ).fetchone()
            changed_plan = con.execute(
                "UPDATE authorized_gather_plans SET "
                "held_cost_micros = held_cost_micros - ?, held_results = held_results - ?, "
                "spent_cost_micros = spent_cost_micros + ?, "
                "settled_results = settled_results + ? WHERE account_digest = ? "
                "AND investigation_digest = ? AND plan_fingerprint = ? RETURNING plan_fingerprint",
                [
                    projected_cost,
                    projected_results,
                    actual_cost_micros,
                    actual_results,
                    *self._scope,
                    plan_fingerprint,
                ],
            ).fetchone()
            if changed_reservation != (reservation_id,) or changed_plan != (plan_fingerprint,):
                raise GatherAuthorityDenied("gather settlement lost reservation conservation")

    def claim(self, *, call_id: str, request_fingerprint: str) -> GatherCallClaim:
        with self._transaction("authorized_gather_claim") as con:
            row = con.execute(
                "SELECT request_fingerprint, state, result_json, failure_code "
                "FROM authorized_gather_call_receipts WHERE account_digest = ? "
                "AND investigation_digest = ? AND call_id = ?",
                [*self._scope, call_id],
            ).fetchone()
            if row is not None:
                if row[0] != request_fingerprint:
                    raise GatherAuthorityDenied("durable gather idempotency key conflict")
                return GatherCallClaim(
                    GatherClaimState(row[1]),
                    _decode_result(row[2]),
                    row[3],
                    False,
                )
            con.execute(
                "INSERT INTO authorized_gather_call_receipts "
                "(account_digest, investigation_digest, call_id, request_fingerprint, state) "
                "VALUES (?, ?, ?, ?, 'claimed')",
                [*self._scope, call_id, request_fingerprint],
            )
            return GatherCallClaim(GatherClaimState.CLAIMED, dispatch_allowed=True)

    def release_unexecuted(self, *, call_id: str, request_fingerprint: str) -> None:
        with self._transaction("authorized_gather_release_claim") as con:
            deleted = con.execute(
                "DELETE FROM authorized_gather_call_receipts WHERE account_digest = ? "
                "AND investigation_digest = ? AND call_id = ? AND request_fingerprint = ? "
                "AND state = 'claimed' RETURNING call_id",
                [*self._scope, call_id, request_fingerprint],
            ).fetchone()
            if deleted != (call_id,):
                raise GatherAuthorityDenied("unexecuted gather claim is missing or terminal")

    def _record_terminal(
        self,
        *,
        call_id: str,
        request_fingerprint: str,
        state: GatherClaimState,
        result: GatherProviderResult | None,
        failure_code: str | None,
    ) -> None:
        with self._transaction(f"authorized_gather_{state.value}") as con:
            changed = con.execute(
                "UPDATE authorized_gather_call_receipts SET state = ?, result_json = ?, "
                "failure_code = ? WHERE account_digest = ? AND investigation_digest = ? "
                "AND call_id = ? AND request_fingerprint = ? AND state = 'claimed' "
                "RETURNING call_id",
                [
                    state.value,
                    None if result is None else _encode_result(result),
                    failure_code,
                    *self._scope,
                    call_id,
                    request_fingerprint,
                ],
            ).fetchone()
            if changed != (call_id,):
                raise GatherAuthorityDenied("gather claim is missing or already terminal")

    def record_succeeded(
        self, *, call_id: str, request_fingerprint: str, result: GatherProviderResult
    ) -> None:
        self._record_terminal(
            call_id=call_id,
            request_fingerprint=request_fingerprint,
            state=GatherClaimState.SUCCEEDED,
            result=result,
            failure_code=None,
        )

    def record_failed(
        self,
        *,
        call_id: str,
        request_fingerprint: str,
        result: GatherProviderResult,
        failure_code: str,
    ) -> None:
        self._record_terminal(
            call_id=call_id,
            request_fingerprint=request_fingerprint,
            state=GatherClaimState.FAILED,
            result=result,
            failure_code=failure_code,
        )

    def record_unknown(self, *, call_id: str, request_fingerprint: str) -> None:
        self._record_terminal(
            call_id=call_id,
            request_fingerprint=request_fingerprint,
            state=GatherClaimState.UNKNOWN,
            result=None,
            failure_code=None,
        )


__all__ = [
    "DuckDBAuthorizedGatherAuthority",
    "ensure_authorized_gather_schema",
    "initialize_authorized_gather_schema",
]
