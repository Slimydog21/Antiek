"""Code named in substrate/dispatch/config.yaml's comments must exist.

The transcription tier's comments once pointed readers at a
``processing.transcription`` cost helper and a
``substrate.dispatch.whisper.WhisperProvider`` that were never written, so a
reader auditing Whisper spend went looking for accounting that does not
happen (LB-12). Every dotted reference to one of this repo's packages in a
comment has to import.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _ROOT / "substrate" / "dispatch" / "config.yaml"
_DOTTED = re.compile(r"\b[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def _repo_packages() -> set[str]:
    return {p.parent.name for p in _ROOT.glob("*/__init__.py")}


def _comment_refs() -> list[tuple[int, str]]:
    packages = _repo_packages()
    refs: list[tuple[int, str]] = []
    for lineno, line in enumerate(_CONFIG.read_text(encoding="utf-8").splitlines(), 1):
        if "#" not in line:
            continue
        comment = line.split("#", 1)[1]
        refs.extend(
            (lineno, m.group(0))
            for m in _DOTTED.finditer(comment)
            if m.group(0).split(".", 1)[0] in packages
        )
    return refs


def _resolves(dotted: str) -> bool:
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for attr in parts[split:]:
            if not hasattr(obj, attr):
                return False
            obj = getattr(obj, attr)
        return True
    return False


def test_config_comments_name_code_that_exists():
    refs = _comment_refs()
    assert refs, "expected the transcription tier to name its Whisper client"
    missing = [f"config.yaml:{lineno} {ref}" for lineno, ref in refs if not _resolves(ref)]
    assert missing == []
