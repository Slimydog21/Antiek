"""Provider registration boot visibility (DRW honest failure)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _candidate_env_paths() -> list[Path]:
    """Ordered dotenv candidates. Explicit ANTIEK_ENV_FILE wins first."""
    out: list[Path] = []
    explicit = os.environ.get("ANTIEK_ENV_FILE", "").strip()
    if explicit:
        out.append(Path(explicit).expanduser())
    here = Path(__file__).resolve()
    repo = here.parents[3]
    out.extend(
        [
            repo / "platform" / ".env",
            repo.parent / "platform" / ".env",
            Path.home() / ".antiek" / ".env",
            Path.cwd() / ".env",
            Path.cwd() / "platform" / ".env",
        ]
    )
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def load_dispatch_env_files(*, override: bool = False) -> list[str]:
    """Load provider API keys from dotenv files into ``os.environ``.

    Returns the list of files that contributed at least one new key.
    Existing environment values win unless ``override=True`` so a
    manually exported key is never clobbered by a stale file.

    Mac Mini uvicorn restarts that skipped ``source platform/.env``
    previously booted with ``registered_providers=[]``, so Loop One
    walked zai→deepseek→xiaomi as three latency=0 "not registered"
    errors and fail-closed with empty decompose.
    """
    loaded_files: list[str] = []
    for path in _candidate_env_paths():
        if not path.is_file():
            continue
        contributed = False
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("dispatch env file unreadable %s: %s", path, exc)
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key or not all(c.isalnum() or c == "_" for c in key):
                continue
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if not override and os.environ.get(key):
                continue
            if value == "" and not override:
                continue
            os.environ[key] = value
            contributed = True
        if contributed:
            loaded_files.append(str(path))
    if loaded_files:
        logger.info(
            "dispatch env loaded from %s (existing process env preserved)",
            ", ".join(loaded_files),
        )
    return loaded_files


def log_zero_providers_warning_if_needed(registered_providers: set[str]) -> None:
    """Loud-but-running boot posture when no dispatch providers registered."""
    if registered_providers:
        logger.info(
            "dispatch providers registered: %s",
            ", ".join(sorted(registered_providers)),
        )
        return
    logger.warning(
        "0 providers registered — LLM features will fail; "
        "set ANTIEK_ENV_FILE or place keys in platform/.env "
        "(auto-loaded at boot) then restart",
    )
