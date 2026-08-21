"""Crash-aware orchestration loop for the local Herdr bridge."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .antiek_client import AntiekHttpError
from .config import BridgeConfig
from .herdr_adapter import AgentAmbiguous, AgentUnavailable, HerdrAdapter, PromptReceipt
from .journal import BridgeJournal, JournalAttempt
from .models import LeaseEnvelope, StructuredResult


class AntiekTransport(Protocol):
    def lease(self) -> LeaseEnvelope | None: ...

    def renew(self, lease: LeaseEnvelope) -> None: ...

    def submitted(self, lease: LeaseEnvelope, *, target: str) -> None: ...

    def acknowledged(self, lease: LeaseEnvelope, *, receipt_sha256: str) -> None: ...

    def working(self, lease: LeaseEnvelope) -> None: ...

    def result(self, result: StructuredResult) -> None: ...


class HerdrTransport(Protocol):
    def prompt(self, lease: LeaseEnvelope, *, result_path: Path) -> PromptReceipt: ...


class BridgeDaemon:
    def __init__(
        self,
        config: BridgeConfig,
        *,
        antiek: AntiekTransport,
        herdr: HerdrTransport,
        journal: BridgeJournal,
    ) -> None:
        self._config = config
        self._antiek = antiek
        self._herdr = herdr
        self._journal = journal
        self._results_dir = config.journal_path.parent / "results"
        self._results_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._results_dir.chmod(0o700)

    def process_once(self) -> None:
        self._flush_results()
        outstanding = self._journal.pending_attempts()
        if outstanding:
            self._resume(outstanding[0])
            return
        lease = self._antiek.lease()
        if lease is None:
            return
        self._journal.record_lease(lease)
        self._dispatch(lease)

    def _flush_results(self) -> None:
        for attempt in self._journal.pending_results():
            if attempt.result is None:  # pragma: no cover - query invariant
                continue
            try:
                self._antiek.result(attempt.result)
            except AntiekHttpError as exc:
                if exc.status != 410:
                    raise
                self._journal.mark_lease_gone(attempt.lease.lease_id)
                continue
            self._journal.mark_callback_delivered(
                attempt.lease.lease_id,
                attempt.result.digest(),
            )

    def _resume(self, attempt: JournalAttempt) -> None:
        if attempt.result is not None:
            return
        if attempt.prompt_receipt_sha256 is None or attempt.target_observed is None:
            self._dispatch(attempt.lease)
            return
        try:
            self._record_remote_progress(attempt)
            self._antiek.renew(attempt.lease)
        except AntiekHttpError as exc:
            if exc.status != 410:
                raise
            self._journal.mark_lease_gone(attempt.lease.lease_id)

    def _record_remote_progress(self, attempt: JournalAttempt) -> None:
        self._antiek.submitted(attempt.lease, target=attempt.target_observed or "unknown")
        self._antiek.acknowledged(
            attempt.lease,
            receipt_sha256=attempt.prompt_receipt_sha256 or "",
        )
        if attempt.prompt_agent_status == "working":
            self._antiek.working(attempt.lease)

    def _dispatch(self, lease: LeaseEnvelope) -> None:
        result_path = self._results_dir / f"{lease.lease_id}.json"
        try:
            receipt = self._herdr.prompt(lease, result_path=result_path)
        except AgentAmbiguous:
            self._capture_delivery_failure(
                lease,
                error_code="herdr_target_ambiguous",
                retryable=False,
            )
            return
        except AgentUnavailable:
            self._capture_delivery_failure(
                lease,
                error_code="herdr_unavailable",
                retryable=True,
            )
            return
        self._journal.record_prompt_receipt(
            lease,
            target=receipt.target,
            receipt_sha256=receipt.receipt_sha256,
            agent_status=receipt.agent_status,
        )
        self._record_remote_progress(self._journal.pending_attempts()[0])

    def _capture_delivery_failure(
        self,
        lease: LeaseEnvelope,
        *,
        error_code: str,
        retryable: bool,
    ) -> None:
        result = StructuredResult.parse(
            {
                "work_id": lease.work_id,
                "lease_id": lease.lease_id,
                "attempt_no": lease.attempt_no,
                "context_sha256": lease.context_sha256,
                "kind": "failure",
                "error_code": error_code,
                "retryable": retryable,
            }
        )
        self._journal.capture_result(result)
        try:
            self._antiek.result(result)
        except AntiekHttpError as exc:
            if exc.status != 410:
                raise
            self._journal.mark_lease_gone(lease.lease_id)
            return
        self._journal.mark_callback_delivered(lease.lease_id, result.digest())

    def run_forever(self) -> None:
        while True:
            self.process_once()
            time.sleep(self._config.poll_seconds)


__all__ = ["BridgeDaemon", "HerdrAdapter"]
