"""Extension loader -- discovers and loads per-project + operator-global extensions."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from substrate.hooks.registry import HookRegistry


@dataclass(frozen=True)
class ExtensionLoadResult:
    extension_id: str
    path: Path
    status: Literal["loaded", "disabled", "failed"]
    error: str | None = None


def _candidate_paths(project_root: Path | None) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    if project_root is not None:
        proj_ext = project_root / "antiek_extensions"
        if proj_ext.is_dir():
            for ext_py in sorted(proj_ext.glob("*/extension.py")):
                candidates.append(("project", ext_py))
    operator_ext = Path.home() / ".antiek" / "extensions"
    if operator_ext.is_dir():
        for ext_py in sorted(operator_ext.glob("*/extension.py")):
            candidates.append(("operator", ext_py))
    return candidates


def _extension_id(scope: str, ext_py: Path) -> str:
    return f"{scope}:{ext_py.parent.name}"


def load_extensions(
    registry: HookRegistry, project_root: Path | None = None,
) -> list[ExtensionLoadResult]:
    results: list[ExtensionLoadResult] = []
    for scope, ext_py in _candidate_paths(project_root):
        ext_id = _extension_id(scope, ext_py)
        if (ext_py.parent / ".disabled").exists():
            results.append(ExtensionLoadResult(extension_id=ext_id, path=ext_py, status="disabled"))
            continue
        try:
            module_name = f"antiek_ext.{scope}.{ext_py.parent.name}"
            spec = importlib.util.spec_from_file_location(module_name, ext_py)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot create spec for {ext_py}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise AttributeError(
                    f"extension {ext_id} missing required `register(registry)` callable"
                )
            register(registry)
            results.append(ExtensionLoadResult(extension_id=ext_id, path=ext_py, status="loaded"))
        except Exception as exc:
            results.append(
                ExtensionLoadResult(
                    extension_id=ext_id, path=ext_py, status="failed", error=repr(exc)
                )
            )
    return results
