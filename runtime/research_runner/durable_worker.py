"""Reference subprocess worker for the durable research execution seam.

It is a proof harness, not production ``HostLocalRunner`` wiring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from substrate.event_log.run_durability_port import RunDurabilityEventLogPort
from substrate.run_durability import CheckpointKind

from .durable_execution import (
    AuthorizedRun,
    DurableWorkSupervisor,
    EffectReceipt,
    WorkUnit,
)


class FileReceiptExecutor:
    """Private-directory receipt store with atomic no-replace publication."""

    def __init__(self, root: Path, *, stop_after_publish: Path | None = None) -> None:
        self._root = root
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self._root.is_symlink() or self._root.stat().st_mode & 0o077:
            raise RuntimeError("receipt directory must be private and must not be a symlink")
        self._stop_after_publish = stop_after_publish
        info = self._root.stat()
        self._root_identity = (info.st_dev, info.st_ino)

    def _open_root_fd(self) -> int:
        try:
            directory_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise RuntimeError("receipt directory changed after executor initialization") from exc
        info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or (info.st_dev, info.st_ino) != self._root_identity
        ):
            os.close(directory_fd)
            raise RuntimeError("receipt directory changed after executor initialization")
        return directory_fd

    def lookup(self, idempotency_key: str) -> EffectReceipt | None:
        directory_fd = self._open_root_fd()
        try:
            return self._lookup_fd(directory_fd, idempotency_key)
        finally:
            os.close(directory_fd)

    def _lookup_fd(self, directory_fd: int, idempotency_key: str) -> EffectReceipt | None:
        key = EffectReceipt(idempotency_key, "receipt:validation").idempotency_key
        name = f"{key}.json"
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink not in {1, 2}
            ):
                raise RuntimeError("unsafe effect receipt")
            raw = os.read(fd, 1025)
            if len(raw) > 1024:
                raise RuntimeError("unsafe effect receipt")
        finally:
            os.close(fd)
        try:
            value = json.loads(raw, object_pairs_hook=self._unique_object)
            if not isinstance(value, dict) or set(value) != {"idempotency_key", "outcome_ref"}:
                raise ValueError
            receipt = EffectReceipt(value["idempotency_key"], value["outcome_ref"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("corrupt effect receipt") from exc
        if receipt.idempotency_key != key:
            raise RuntimeError("cross-effect receipt")
        canonical = json.dumps(
            {"idempotency_key": receipt.idempotency_key, "outcome_ref": receipt.outcome_ref},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if raw != canonical:
            raise RuntimeError("effect receipt is not canonical JSON")
        if info.st_nlink == 2:
            aliases: list[str] = []
            for candidate in os.listdir(directory_fd):
                if not candidate.startswith(".receipt-tmp-"):
                    continue
                candidate_info = os.stat(candidate, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISREG(candidate_info.st_mode) and (
                    candidate_info.st_dev,
                    candidate_info.st_ino,
                ) == (info.st_dev, info.st_ino):
                    aliases.append(candidate)
            if len(aliases) != 1:
                raise RuntimeError("receipt has an unexplained hard link")
            os.unlink(aliases[0], dir_fd=directory_fd)
            os.fsync(directory_fd)
        return receipt

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate receipt key")
            result[key] = value
        return result

    def execute(self, unit: WorkUnit, *, idempotency_key: str) -> EffectReceipt:
        directory_fd = self._open_root_fd()
        outcome = hashlib.sha256(f"{unit.boundary.value}:{idempotency_key}".encode()).hexdigest()
        receipt = EffectReceipt(idempotency_key, f"artifact:sha256:{outcome}")
        payload = json.dumps(
            {"idempotency_key": receipt.idempotency_key, "outcome_ref": receipt.outcome_ref},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        final_name = f"{idempotency_key}.json"
        temporary = f".receipt-tmp-{secrets.token_hex(32)}"
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short receipt write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(
                    temporary,
                    final_name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = self._lookup_fd(directory_fd, idempotency_key)
                if existing is None:
                    raise RuntimeError("receipt publication raced without a winner") from None
                return existing
            os.fsync(directory_fd)
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory_fd)
            os.close(directory_fd)
        if self._stop_after_publish is not None and not self._stop_after_publish.exists():
            self._stop_after_publish.write_text(idempotency_key)
            os.kill(os.getpid(), signal.SIGSTOP)
        return receipt


def _units() -> tuple[WorkUnit, ...]:
    return (
        WorkUnit(CheckpointKind.SOURCES_READY, {"query_ref": "query:approved"}),
        WorkUnit(CheckpointKind.NOTES_READY, {"sources_ref": "sources:approved"}),
        WorkUnit(CheckpointKind.SYNTHESIS_READY, {"notes_ref": "notes:approved"}),
        WorkUnit(CheckpointKind.REPORT_READY, {"synthesis_ref": "synthesis:approved"}),
    )


def _ensure_private_worker_root(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if (
        root.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RuntimeError("worker root must be a private current-user directory")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--approved-brief-hash", required=True)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--stop-marker", type=Path)
    args = parser.parse_args()
    _ensure_private_worker_root(args.root)
    units = _units()
    authorization = AuthorizedRun(
        args.run_id,
        args.approved_brief_hash,
        "brief:approved",
        "plan:approved",
        DurableWorkSupervisor.work_plan_hash(units),
    )
    supervisor = DurableWorkSupervisor(
        RunDurabilityEventLogPort(args.root / "events"),
        FileReceiptExecutor(args.root / "receipts", stop_after_publish=args.stop_marker),
        authorization,
        clock=lambda: datetime.now(UTC),
    )
    if args.recover:
        supervisor.recover_interrupted()
    print(supervisor.execute(units), flush=True)


if __name__ == "__main__":
    main()
