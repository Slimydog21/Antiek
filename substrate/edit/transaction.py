"""EditTransaction -- batch edits + commit-boundary validation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from substrate.hooks import HookContext, HookRegistry
from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import current_burn_context


def edit_validator_seam_id() -> str:
    return "edit_validator"


def declare_edit_validator_seam(registry: HookRegistry) -> None:
    registry.declare_seam(
        edit_validator_seam_id(),
        "Validate the set of files modified by an EditTransaction. "
        "Post hooks receive (paths: list[Path], result: list[str]) and return a list of error strings.",
    )


class TransactionNotEntered(RuntimeError):
    pass


class TransactionAlreadyCommitted(RuntimeError):
    pass


class FileNotReserved(RuntimeError):
    pass


class OldStringNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class PendingEdit:
    path: Path
    old_str: str
    new_str: str
    occurrence: int = 1


@dataclass(frozen=True)
class CommitResult:
    committed: bool
    files_changed: tuple[Path, ...]
    validation_errors: tuple[str, ...] = field(default_factory=tuple)
    rolled_back: bool = False
    error: str | None = None


class EditTransaction:
    def __init__(
        self,
        paths: list[Path],
        *,
        registry: HookRegistry | None = None,
    ) -> None:
        self._reserved: frozenset[Path] = frozenset(p.resolve() for p in paths)
        self._pending: list[PendingEdit] = []
        self._committed = False
        self._entered = False
        self._registry = registry
        self._snapshots: dict[Path, bytes | None] = {}

    def __enter__(self) -> "EditTransaction":
        for p in self._reserved:
            self._snapshots[p] = p.read_bytes() if p.exists() else None
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None and not self._committed:
            self.rollback()
        return False

    def edit(
        self, path: Path | str, old_str: str, new_str: str, *, occurrence: int = 1
    ) -> None:
        if not self._entered:
            raise TransactionNotEntered(
                "EditTransaction.edit called before __enter__; "
                "use as `with EditTransaction(...) as tx: tx.edit(...)`"
            )
        if self._committed:
            raise TransactionAlreadyCommitted(
                "transaction already committed; call .amend() to reopen"
            )
        p = Path(path).resolve()
        if p not in self._reserved:
            raise FileNotReserved(
                f"{p} not in reserved paths {sorted(self._reserved)}; "
                f"all paths must be declared at EditTransaction construction"
            )
        if occurrence < 1:
            raise ValueError(f"occurrence must be >= 1, got {occurrence}")
        if old_str == "":
            raise ValueError(
                "old_str must not be empty; EditTransaction does not create files. "
                "Create the file first, then reserve and edit it."
            )
        self._pending.append(PendingEdit(p, old_str, new_str, occurrence))

    def commit(self) -> CommitResult:
        if not self._entered:
            raise TransactionNotEntered("commit before __enter__")
        if self._committed:
            raise TransactionAlreadyCommitted()

        staged: dict[Path, str] = {}
        for edit in self._pending:
            current = staged.get(edit.path)
            if current is None:
                current = (
                    edit.path.read_text(encoding="utf-8") if edit.path.exists() else ""
                )
            parts = current.split(edit.old_str)
            if len(parts) - 1 < edit.occurrence:
                self.rollback()
                self._emit_burn(error=f"{edit.path}: old_str not found")
                return CommitResult(
                    committed=False,
                    files_changed=(),
                    validation_errors=(
                        f"{edit.path}: old_str not found "
                        f"(need occurrence {edit.occurrence}, file has {len(parts) - 1})",
                    ),
                    rolled_back=True,
                    error="OldStringNotFound",
                )
            new_content = (
                edit.old_str.join(parts[: edit.occurrence])
                + edit.new_str
                + edit.old_str.join(parts[edit.occurrence :])
            )
            staged[edit.path] = new_content

        for path, content in staged.items():
            path.write_text(content, encoding="utf-8")

        errs = self._run_validators(list(staged.keys()))
        files_changed = tuple(staged.keys())
        self._committed = True
        self._emit_burn(error=None, files_changed=files_changed, validation_errors=errs)

        return CommitResult(
            committed=True,
            files_changed=files_changed,
            validation_errors=tuple(errs),
        )

    def amend(self) -> "EditTransaction":
        if not self._entered:
            raise TransactionNotEntered("amend before __enter__")
        self._committed = False
        self._pending = []
        return self

    def rollback(self) -> None:
        for path, content in self._snapshots.items():
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(content)
        self._pending = []

    def _run_validators(self, paths: list[Path]) -> list[str]:
        if self._registry is None:
            return []
        seam = edit_validator_seam_id()
        if seam not in self._registry.seams():
            return []
        ctx = HookContext(
            seam_id=seam,
            extension_id="core",
            call_id=f"edit-tx-{int(time.time() * 1e6)}",
        )

        def _primitive(**kw: Any) -> list[str]:
            return []

        result = self._registry.dispatch(seam, ctx, _primitive, paths=paths)
        return list(result) if result else []

    def _emit_burn(self, *, error, files_changed=(), validation_errors=()):
        try:
            ctx = current_burn_context()
        except Exception:
            return
        recorder = BurnRecorder.for_project(ctx.project_root)
        recorder.record(
            BurnEvent(
                session_id=ctx.session_id,
                project_id=ctx.project_id,
                call_id=f"edit-tx-{int(time.time() * 1e6)}",
                model="n/a",
                tool_id="edit_transaction",
                input_tokens=len(self._pending),
                output_tokens=len(files_changed),
                error=error or (f"validation_errors={len(validation_errors)}" if validation_errors else None),
                extension_ids_active=ctx.extension_ids_active,
            )
        )
