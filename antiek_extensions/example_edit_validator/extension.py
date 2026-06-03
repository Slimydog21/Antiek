"""example_edit_validator — post-hook on edit_validator that records the
paths touched by every EditTransaction commit.

The extension owns its own state (a counter dict on the hook instance);
the hook accumulates without leaking to siblings.
"""

from __future__ import annotations

from pathlib import Path

from substrate.hooks import HookContext, HookRegistry


class _RecordingValidator:
    def __init__(self) -> None:
        self.commits: int = 0
        self.paths_touched: list[Path] = []

    def __call__(
        self, ctx: HookContext, result: list[str], *, paths: list[Path],
    ) -> list[str]:
        self.commits += 1
        self.paths_touched.extend(paths)
        return list(result)


def register(registry: HookRegistry) -> None:
    registry.register_hook(
        seam_id="edit_validator",
        hook=_RecordingValidator(),
        stage="post",
        extension_id="example_edit_validator:v1",
        priority=0,
    )
