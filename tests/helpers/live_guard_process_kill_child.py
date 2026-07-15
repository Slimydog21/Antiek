from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

from substrate.multimedia.bedrock_live_guard_acquisition import (
    LiveGuardAcquisitionAttempt,
    LiveGuardAcquisitionCoordinator,
)
from substrate.multimedia.bedrock_live_guard_journal import SqliteLiveGuardAcquisitionJournal
from tests.test_multimedia_bedrock_live_guard_acquisition import _command, _coordinator
from tests.test_multimedia_bedrock_live_guard_journal import _complete_with_coordinator

_NOW = datetime(2026, 7, 15, 1, tzinfo=UTC)
_RECOVERY_NOW = datetime(2026, 7, 15, 1, 0, 30, tzinfo=UTC)
_NONCE = "c" * 32
_JOURNAL_STAGES = {
    "after_command_insert",
    "after_attempt_insert",
    "before_intent_commit",
    "after_intent_commit",
    "after_completion_insert",
    "before_completion_commit",
    "after_completion_commit",
}
_ACQUISITION_STAGES = {
    "after_intent_commit",
    "before_initial_scp_describe",
    "before_initial_scp_targets",
    "before_initial_rcp_describe",
    "before_initial_rcp_targets",
    "before_attestation",
    "before_qualification",
    "before_final_scp_describe",
    "before_final_scp_targets",
    "before_final_rcp_describe",
    "before_final_rcp_targets",
    "before_revocation",
    "before_revocation_verify",
    "after_completion_insert",
    "before_completion_commit",
    "after_completion_commit",
}


def _private_directory(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or path.resolve() != path:
        raise ValueError("directory is unsafe")
    metadata = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ValueError("directory must be private mode 0700")
    return path


class Checkpoint:
    def __init__(
        self,
        *,
        control_root: Path,
        store_root: Path,
        mode: str,
        stage: str,
        command_id: str,
        attempt_id: str,
    ) -> None:
        self.control_root = control_root
        self.store_root = store_root
        self.mode = mode
        self.stage = stage
        self.command_id = command_id
        self.attempt_id = attempt_id
        self.reached = False

    def __call__(self, stage: str) -> None:
        if stage != self.stage:
            return
        if self.reached:
            raise RuntimeError("checkpoint was reached more than once")
        self.reached = True
        receipt_digest = None
        if stage == "after_completion_commit":
            receipt = SqliteLiveGuardAcquisitionJournal(self.store_root).read_attempt(
                attempt_id=self.attempt_id
            )
            if receipt is None:
                raise RuntimeError("post-commit checkpoint lacks exact receipt")
            receipt_digest = hashlib.sha256(receipt.encode("ascii")).hexdigest()
        marker = self.control_root / "checkpoint.json"
        payload = json.dumps(
            {
                "attempt_id": self.attempt_id,
                "checkpoint": stage,
                "command_id": self.command_id,
                "mode": self.mode,
                "pid": os.getpid(),
                "receipt_digest": receipt_digest,
                "schema_version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(self.control_root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        ready_payload = json.dumps(
            {
                "checkpoint": stage,
                "marker_digest": hashlib.sha256(payload).hexdigest(),
                "pid": os.getpid(),
                "schema_version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        ready = self.control_root / "checkpoint.ready.json"
        ready_descriptor = os.open(ready, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(ready_descriptor, ready_payload)
            os.fsync(ready_descriptor)
        finally:
            os.close(ready_descriptor)
        directory = os.open(self.control_root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        while True:
            signal.pause()


def _identity():
    cycle34 = _coordinator(_NOW)[0]
    command = _command(cycle34)
    trusted_start = "2026-07-15T01:00:00Z"
    attempt = LiveGuardAcquisitionAttempt(
        command_digest=command.digest,
        attempt_id="lga_"
        + hashlib.sha256(
            f"{command.digest}:{trusted_start}:{_NONCE}".encode("ascii")
        ).hexdigest(),
        attempt_nonce=_NONCE,
        trusted_start=trusted_start,
    )
    return cycle34, command, attempt


def _run_journal(root: Path, control: Path, stage: str) -> None:
    if stage not in _JOURNAL_STAGES:
        raise ValueError("unsupported journal checkpoint")
    cycle34, command, attempt = _identity()
    checkpoint = Checkpoint(
        control_root=control,
        store_root=root,
        mode="journal",
        stage=stage,
        command_id=command.command_id,
        attempt_id=attempt.attempt_id,
    )
    journal = SqliteLiveGuardAcquisitionJournal(root, failure_hook=checkpoint)
    journal.record_intent(command_json=command.canonical_json, attempt_json=attempt.canonical_json)
    if stage in {
        "after_command_insert",
        "after_attempt_insert",
        "before_intent_commit",
        "after_intent_commit",
    }:
        raise RuntimeError("journal checkpoint was not reached")
    source = root / "receipt-source"
    source.mkdir(mode=0o700)
    _, receipt = _complete_with_coordinator(SqliteLiveGuardAcquisitionJournal(source))
    if receipt.attempt_id != attempt.attempt_id or receipt.cycle34_receipt_digest != cycle34.digest:
        raise RuntimeError("completion fixture conflicts")
    journal.commit_attempt(attempt_id=attempt.attempt_id, receipt_json=receipt.canonical_json)
    raise RuntimeError("journal checkpoint was not reached")


class OrganizationsCheckpoint:
    def __init__(self, wrapped: object, checkpoint: Checkpoint) -> None:
        self.wrapped = wrapped
        self.checkpoint = checkpoint
        self.calls = 0

    def _stage(self, operation: str) -> str:
        labels = ("initial_scp", "initial_scp", "initial_rcp", "initial_rcp", "final_scp", "final_scp", "final_rcp", "final_rcp")
        label = labels[self.calls]
        self.calls += 1
        return f"before_{label}_{operation}"

    def describe_policy(self, **request: object):
        self.checkpoint(self._stage("describe"))
        return self.wrapped.describe_policy(**request)

    def list_targets_for_policy(self, **request: object):
        self.checkpoint(self._stage("targets"))
        return self.wrapped.list_targets_for_policy(**request)


class CustodyCheckpoint:
    def __init__(self, wrapped: object, checkpoint: Checkpoint) -> None:
        self.wrapped = wrapped
        self.checkpoint = checkpoint

    def acquire_attestation(self, **request: object):
        self.checkpoint("before_attestation")
        return self.wrapped.acquire_attestation(**request)


class QualifierCheckpoint:
    def __init__(self, wrapped: object, checkpoint: Checkpoint) -> None:
        self.wrapped = wrapped
        self.checkpoint = checkpoint

    def qualify(self, **request: object):
        self.checkpoint("before_qualification")
        return self.wrapped.qualify(**request)


class RevocationCheckpoint:
    def __init__(self, wrapped: object, checkpoint: Checkpoint) -> None:
        self.wrapped = wrapped
        self.checkpoint = checkpoint

    def observe_revocation(self, **request: object):
        self.checkpoint("before_revocation")
        return self.wrapped.observe_revocation(**request)


class VerifierCheckpoint:
    def __init__(self, wrapped: object, checkpoint: Checkpoint) -> None:
        self.wrapped = wrapped
        self.checkpoint = checkpoint

    @property
    def verifier_digest(self) -> str:
        return self.wrapped.verifier_digest

    @property
    def trust_root_digest(self) -> str:
        return self.wrapped.trust_root_digest

    def verify(self, observation: object):
        self.checkpoint("before_revocation_verify")
        return self.wrapped.verify(observation)


def _run_acquisition(root: Path, control: Path, stage: str) -> None:
    if stage not in _ACQUISITION_STAGES:
        raise ValueError("unsupported acquisition checkpoint")
    cycle34, command, attempt = _identity()
    checkpoint = Checkpoint(
        control_root=control,
        store_root=root,
        mode="acquire",
        stage=stage,
        command_id=command.command_id,
        attempt_id=attempt.attempt_id,
    )
    _, base, organizations, custody, revocations, verifier, _, _ = _coordinator(_NOW)
    journal = SqliteLiveGuardAcquisitionJournal(root, failure_hook=checkpoint)
    coordinator = LiveGuardAcquisitionCoordinator(
        organizations=OrganizationsCheckpoint(organizations, checkpoint),
        custody=CustodyCheckpoint(custody, checkpoint),
        revocations=RevocationCheckpoint(revocations, checkpoint),
        revocation_verifier=VerifierCheckpoint(verifier, checkpoint),
        qualifier=QualifierCheckpoint(base.qualifier, checkpoint),
        journal=journal,
        clock=lambda: _NOW,
        approved_revocation_verifier_digest=base.approved_revocation_verifier_digest,
        approved_revocation_trust_root_digest=base.approved_revocation_trust_root_digest,
        approved_audit_source_digest=base.approved_audit_source_digest,
    )
    coordinator.acquire(command=command, cycle34_receipt=cycle34, attempt_nonce=_NONCE)
    raise RuntimeError("acquisition checkpoint was not reached")


def _inspect(root: Path) -> None:
    journal = SqliteLiveGuardAcquisitionJournal(root)
    report = journal.verify_all()
    _, command, attempt = _identity()
    status = "absent"
    receipt_digest = None
    try:
        intent = journal.read_intent(attempt_id=attempt.attempt_id)
    except Exception as exc:
        if report.attempt_count != 0:
            raise RuntimeError("expected attempt is unavailable") from exc
    else:
        if intent.command != command or intent.attempt != attempt:
            raise RuntimeError("inspected intent conflicts")
        status = "completed" if intent.completed else "in_progress"
        if intent.completed:
            receipt = journal.read_attempt(attempt_id=attempt.attempt_id)
            if receipt is None:
                raise RuntimeError("completed intent lacks receipt")
            receipt_digest = hashlib.sha256(receipt.encode("ascii")).hexdigest()
    print(
        json.dumps(
            {
                "attempt_count": report.attempt_count,
                "attempt_id": attempt.attempt_id,
                "command_count": report.command_count,
                "completion_count": report.completion_count,
                "production_eligible": False,
                "receipt_digest": receipt_digest,
                "status": status,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _recover(root: Path) -> None:
    cycle34, command, attempt = _identity()
    _, base, organizations, custody, revocations, verifier, _, calls = _coordinator(_RECOVERY_NOW)
    revocations.watermark = "2026-07-15T01:00:00Z"
    journal = SqliteLiveGuardAcquisitionJournal(root)
    intent = journal.read_intent(attempt_id=attempt.attempt_id)
    if intent.completed:
        if calls:
            raise RuntimeError("historical classification made external calls")
        print('{"external_call_count":0,"recovery":"historical"}', flush=True)
        return
    coordinator = LiveGuardAcquisitionCoordinator(
        organizations=organizations,
        custody=custody,
        revocations=revocations,
        revocation_verifier=verifier,
        qualifier=base.qualifier,
        journal=journal,
        clock=lambda: _RECOVERY_NOW,
        approved_revocation_verifier_digest=base.approved_revocation_verifier_digest,
        approved_revocation_trust_root_digest=base.approved_revocation_trust_root_digest,
        approved_audit_source_digest=base.approved_audit_source_digest,
    )
    receipt = coordinator.acquire(
        command=command,
        cycle34_receipt=cycle34,
        attempt_nonce=attempt.attempt_nonce,
        attempt_started_at=attempt.trusted_start,
    )
    print(
        json.dumps(
            {
                "attempt_id": receipt.attempt_id,
                "completed_at": receipt.completed_at,
                "external_call_count": len(calls),
                "revocation_observed_at": receipt.revocation_observed_at,
                "recovery": "completed",
                "trusted_start": receipt.trusted_start,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("journal", "acquire", "inspect", "recover"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--control-root")
    parser.add_argument("--stage")
    args = parser.parse_args()
    root = _private_directory(args.root)
    if args.mode in {"journal", "acquire"}:
        if args.control_root is None or args.stage is None:
            raise ValueError("kill mode requires control root and stage")
        control = _private_directory(args.control_root)
        if args.mode == "journal":
            _run_journal(root, control, args.stage)
        else:
            _run_acquisition(root, control, args.stage)
    elif args.control_root is not None or args.stage is not None:
        raise ValueError("inspection mode rejects control arguments")
    elif args.mode == "inspect":
        _inspect(root)
    else:
        _recover(root)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"controlled child failure: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(2) from None
