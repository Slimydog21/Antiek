"""HookRegistry — the runtime registry of declared seams and attached hooks."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Literal

from substrate.hooks.contract import (
    HookContext,
    HookShortCircuit,
    OnErrorHook,
    PostCallHook,
    PreCallHook,
)

Stage = Literal["pre", "post", "err"]

_PROTOCOLS: dict[Stage, type] = {"pre": PreCallHook, "post": PostCallHook, "err": OnErrorHook}


@dataclass(frozen=True)
class _Entry:
    hook: Any
    extension_id: str
    priority: int
    seq: int


class HookRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._seams: dict[str, str] = {}
        self._pre: dict[str, list[_Entry]] = {}
        self._post: dict[str, list[_Entry]] = {}
        self._err: dict[str, list[_Entry]] = {}
        self._seq = 0

    def declare_seam(self, seam_id: str, description: str = "") -> None:
        with self._lock:
            if seam_id in self._seams:
                raise ValueError(f"seam {seam_id!r} already declared")
            self._seams[seam_id] = description

    def seams(self) -> dict[str, str]:
        with self._lock:
            return dict(self._seams)

    def register_hook(
        self, seam_id: str, hook: Any, stage: Stage, extension_id: str, priority: int = 0,
    ) -> None:
        if stage not in _PROTOCOLS:
            raise ValueError(f"stage must be one of {list(_PROTOCOLS)}, got {stage!r}")
        proto = _PROTOCOLS[stage]
        if not isinstance(hook, proto):
            raise TypeError(
                f"hook {hook!r} does not satisfy Protocol {proto.__name__} for stage {stage!r}"
            )
        with self._lock:
            if seam_id not in self._seams:
                raise KeyError(f"seam {seam_id!r} not declared; declare_seam() first")
            self._seq += 1
            entry = _Entry(hook, extension_id, priority, self._seq)
            target = self._by_stage(stage)
            target.setdefault(seam_id, []).append(entry)
            target[seam_id].sort(key=lambda e: (e.priority, e.seq))

    def _by_stage(self, stage: Stage) -> dict[str, list[_Entry]]:
        return {"pre": self._pre, "post": self._post, "err": self._err}[stage]

    def dispatch_pre(self, seam_id: str, ctx: HookContext, /, **kwargs: Any) -> dict[str, Any]:
        snapshot = self._snapshot(self._pre, seam_id)
        for entry in snapshot:
            updated = entry.hook(ctx, **kwargs)
            if updated is not None:
                kwargs = updated
        return kwargs

    def dispatch_post(self, seam_id: str, ctx: HookContext, result: Any, /, **kwargs: Any) -> Any:
        snapshot = self._snapshot(self._post, seam_id)
        for entry in snapshot:
            result = entry.hook(ctx, result, **kwargs)
        return result

    def dispatch_error(self, seam_id: str, ctx: HookContext, exc: BaseException, /, **kwargs: Any) -> Any:
        snapshot = self._snapshot(self._err, seam_id)
        for entry in snapshot:
            recovered = entry.hook(ctx, exc, **kwargs)
            if recovered is not None:
                return recovered
        raise exc

    def _snapshot(self, target: dict[str, list[_Entry]], seam_id: str) -> tuple[_Entry, ...]:
        with self._lock:
            return tuple(target.get(seam_id, ()))

    def dispatch(self, seam_id: str, ctx: HookContext, primitive, /, **kwargs: Any) -> Any:
        try:
            kwargs = self.dispatch_pre(seam_id, ctx, **kwargs)
        except HookShortCircuit as sc:
            return self.dispatch_post(seam_id, ctx, sc.result, **kwargs)
        try:
            result = primitive(**kwargs)
        except BaseException as exc:
            result = self.dispatch_error(seam_id, ctx, exc, **kwargs)
        return self.dispatch_post(seam_id, ctx, result, **kwargs)

    def list_hooks(self, seam_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock:
            for stage_name, target in (("pre", self._pre), ("post", self._post), ("err", self._err)):
                for sid, entries in target.items():
                    if seam_id is not None and sid != seam_id:
                        continue
                    for e in entries:
                        rows.append({
                            "seam_id": sid, "stage": stage_name,
                            "extension_id": e.extension_id, "priority": e.priority,
                            "seq": e.seq, "hook_repr": repr(e.hook),
                        })
        return rows
