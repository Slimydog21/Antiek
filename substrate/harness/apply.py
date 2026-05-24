"""apply_harness -- compose a working substrate session from a fork."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]

from substrate.conversation.compaction import compact as compact_fn  # noqa: F401
from substrate.conversation.policy import CompactionConfig, CompactionPolicy
from substrate.conversation.token_counter import declare_token_count_seam
from substrate.edit.transaction import declare_edit_validator_seam
from substrate.harness.fork import HarnessFork
from substrate.harness_diff import HarnessSnapshot, capture_snapshot, save_snapshot
from substrate.hooks import (
    ExtensionLoadResult,
    HookRegistry,
    load_extensions,
)
from substrate.queue import BoundedQueue, get_registry as get_queue_registry
from substrate.tools.adapter_map import build_import_map


@dataclass(frozen=True)
class HarnessApplyResult:
    registry: HookRegistry
    extension_results: tuple[ExtensionLoadResult, ...]
    compaction_config: CompactionConfig
    queue_names: tuple[str, ...]
    import_map: dict
    snapshot: HarnessSnapshot
    snapshot_path: Path | None = None


def _declare_standard_seams(registry: HookRegistry) -> None:
    declare_token_count_seam(registry)
    declare_edit_validator_seam(registry)
    for seam in (
        "message_formatter",
        "model_select",
        "tool_dispatch",
        "run_script_dispatch",
        "compaction_summarize",
    ):
        if seam not in registry.seams():
            registry.declare_seam(seam, f"standard substrate seam: {seam}")


def _load_fork_config(fork: HarnessFork) -> dict:
    cfg = fork.path / "config.toml"
    if not cfg.exists():
        return {}
    try:
        return tomllib.loads(cfg.read_text())
    except Exception:
        return {}


def _compaction_from_data(data: dict) -> CompactionConfig:
    c = data.get("compaction", {}) or {}
    return CompactionConfig(
        policy=CompactionPolicy(c.get("policy", "strict")),
        threshold_pct=float(c.get("threshold_pct", 0.85)),
        keep_first_n=int(c.get("keep_first_n", 4)),
        keep_last_n=int(c.get("keep_last_n", 8)),
        summary_model=c.get("summary_model"),
    )


def _queues_from_data(data: dict) -> list[BoundedQueue]:
    queues_section = data.get("queues", {}) or {}
    out: list[BoundedQueue] = []
    qreg = get_queue_registry()
    for name, conf in queues_section.items():
        if not isinstance(conf, dict):
            continue
        try:
            cap = int(conf.get("capacity", 0))
            wm = float(conf.get("watermark_pct", 0.8))
        except (TypeError, ValueError):
            continue
        if cap < 1:
            continue
        q = BoundedQueue(name, capacity=cap, watermark_pct=wm)
        try:
            qreg.register(q)
        except ValueError:
            q = qreg.get(name)
        out.append(q)
    return out


def apply_harness(
    *,
    project_root: Path,
    fork_name: str | None = None,
    capture_tag: str | None = None,
) -> HarnessApplyResult:
    registry = HookRegistry()
    _declare_standard_seams(registry)

    ext_results = load_extensions(registry, project_root=project_root)
    if fork_name is not None:
        registry = HookRegistry()
        _declare_standard_seams(registry)
        fork_dir = project_root / "antiek_extensions" / fork_name
        if not (fork_dir / "extension.py").is_file():
            raise FileNotFoundError(f"no fork named {fork_name!r} at {fork_dir}")
        import importlib.util

        module_name = f"antiek_ext.project.{fork_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, fork_dir / "extension.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            module.register(registry)
            ext_results = (
                ExtensionLoadResult(
                    extension_id=f"project:{fork_name}",
                    path=fork_dir / "extension.py",
                    status="loaded",
                ),
            )
        except Exception as exc:
            ext_results = (
                ExtensionLoadResult(
                    extension_id=f"project:{fork_name}",
                    path=fork_dir / "extension.py",
                    status="failed",
                    error=repr(exc),
                ),
            )
    else:
        ext_results = tuple(ext_results)

    compaction_cfg = CompactionConfig()
    queues: list[BoundedQueue] = []
    if fork_name is not None:
        fork = HarnessFork.from_path(project_root / "antiek_extensions" / fork_name)
        data = _load_fork_config(fork)
        compaction_cfg = _compaction_from_data(data)
        queues = _queues_from_data(data)

    import_map = build_import_map(project_root)

    snap = capture_snapshot(
        tag=capture_tag or "apply-snapshot",
        registry=registry,
        model_config={"compaction_policy": compaction_cfg.policy.value},
        tools=[
            {"name": "run_script", "description": "Execute TS in deno sandbox"},
            {"name": "edit_transaction", "description": "Batch file edits with commit-boundary validation"},
        ],
        project_root=project_root,
    )

    snapshot_path: Path | None = None
    if capture_tag is not None:
        snapshot_path = save_snapshot(snap, project_root)

    return HarnessApplyResult(
        registry=registry,
        extension_results=tuple(ext_results),
        compaction_config=compaction_cfg,
        queue_names=tuple(q.name for q in queues),
        import_map=import_map,
        snapshot=snap,
        snapshot_path=snapshot_path,
    )
