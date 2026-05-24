"""Adapter import-map builder -- discovers extension-provided TS adapters."""

from __future__ import annotations

import json
from pathlib import Path


class DuplicateAdapterName(ValueError):
    pass


def build_import_map(project_root: Path) -> dict:
    imports: dict[str, str] = {}
    sources: dict[str, Path] = {}
    ext_root = project_root / "antiek_extensions"
    if not ext_root.is_dir():
        return {"imports": imports}
    for ext_dir in sorted(p for p in ext_root.iterdir() if p.is_dir()):
        adapters_dir = ext_dir / "adapters"
        if not adapters_dir.is_dir():
            continue
        for adapter_dir in sorted(p for p in adapters_dir.iterdir() if p.is_dir()):
            entry = None
            for cand in ("index.ts", "index.js", "mod.ts"):
                p = adapter_dir / cand
                if p.is_file():
                    entry = p
                    break
            if entry is None:
                continue
            name = adapter_dir.name
            if name in imports:
                raise DuplicateAdapterName(
                    f"duplicate adapter name {name!r}: {sources[name]} vs {entry}"
                )
            imports[name] = entry.resolve().as_uri()
            sources[name] = entry
    return {"imports": imports}


def write_import_map(project_root: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(build_import_map(project_root), indent=2, sort_keys=True))
    return dest
