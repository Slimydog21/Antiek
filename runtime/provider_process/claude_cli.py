"""Claude Code process delegation with a private ``CLAUDE_CONFIG_DIR``.

SPR-02 ("Official local harness") adopted this from T3Code: instead of holding a
Claude.ai token, spawn the **unmodified** ``claude`` binary and let it own login
and provider traffic.  Isolation is a per-instance configuration directory, so
two instances cannot see each other's session, and the operator's own
``~/.claude`` is never used, read, symlinked or copied.

Three properties this module exists to guarantee:

1. **A private home or nothing.**  ``CLAUDE_CONFIG_DIR`` comes from the caller and
   must be non-empty.  An empty or missing value fails closed with
   :class:`ClaudeHomeNotConfigured`; it never falls back to ``HOME``, to
   ``$HOME``, or to ``~/.claude``.
2. **No token custody.**  The child environment is built from an allowlist
   (``PATH``, ``LANG``, ``LC_ALL``) plus ``CLAUDE_CONFIG_DIR`` — the same pattern
   ``runtime/prime_agent/process.py`` uses — so credential material in the parent
   environment cannot leak in by default.  Nothing here reads, copies or writes
   token rows; there is no server-side credential in this path at all.
3. **Availability is per instance.**  A probe is keyed by *binary path plus the
   resolved home*, not by a process-global flag, so an instance that is
   unconfigured cannot be masked by another instance that is working.

Argv is the binary plus the caller's arguments, nothing else: no credential
flags, no wrapper that injects an operator login.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ClaudeBinaryUnavailable",
    "ClaudeHomeNotConfigured",
    "ClaudeHomeRefused",
    "ClaudeProcessConfig",
    "ClaudeProcessError",
    "ClaudeProbeResult",
    "DEFAULT_BINARY",
    "build_argv",
    "build_environment",
    "probe",
    "resolve_config_dir",
    "run",
]

DEFAULT_BINARY: str = "claude"

# The parent-environment variables a child is allowed to inherit.  An allowlist,
# not a denylist: anything not named here — ANTHROPIC_API_KEY,
# CLAUDE_CODE_OAUTH_TOKEN, and whatever the next credential is called — does not
# reach the child, so leakage needs an explicit act rather than a missed entry.
_INHERITED_ENV_KEYS: tuple[str, ...] = ("PATH", "LANG", "LC_ALL")

_FLAG = "CLAUDE_CONFIG_DIR"


class ClaudeProcessError(RuntimeError):
    """Base type for refusals from this seam."""


class ClaudeHomeNotConfigured(ClaudeProcessError):
    """No private configuration directory was supplied.

    Raised instead of guessing a home.  A process that silently inherits the
    operator's ``~/.claude`` would read and write their real session.
    """


class ClaudeHomeRefused(ClaudeProcessError):
    """The supplied directory is the operator's own Claude home."""


class ClaudeBinaryUnavailable(ClaudeProcessError):
    """The binary could not be found or did not answer for this home."""


@dataclass(frozen=True, slots=True)
class ClaudeProcessConfig:
    """Everything needed to spawn one instance, and nothing else.

    ``home_path`` is the caller-owned configuration directory.  It is required:
    there is no default, because a default would be someone's real home.
    """

    home_path: Path | str
    binary: str = DEFAULT_BINARY
    cwd: Path | None = None
    timeout_seconds: float = 120.0
    environ: Mapping[str, str] | None = field(default=None, repr=False)
    extra_arguments: Sequence[str] = ()

    def __post_init__(self) -> None:
        # Validate at construction so a misconfigured instance is rejected where it
        # is created, rather than at the moment a child would have been spawned.
        _private_home(str(self.home_path))
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")


@dataclass(frozen=True, slots=True)
class ClaudeProbeResult:
    """Typed availability for one (binary, home) pair."""

    available: bool
    binary: str
    config_dir: str
    binary_path: str | None = None
    version: str = ""
    detail: str = ""


def _private_home(raw: str) -> Path:
    """Validate a caller-supplied configuration directory and resolve it.

    The single place the contract is enforced, so construction, probing and
    spawning cannot disagree about what a valid home is.  An empty or missing
    value is refused outright: the fallback it would otherwise take — ``HOME``,
    ``$HOME`` or ``~/.claude`` — is the operator's real Claude session.
    """
    if not raw.strip():
        raise ClaudeHomeNotConfigured(
            "home_path is empty: supply a private CLAUDE_CONFIG_DIR for this instance. "
            "This seam has no default home by design — falling back to HOME would point "
            "the child at the operator's real ~/.claude."
        )
    resolved = Path(raw).expanduser().resolve()
    operator_home = (Path("~/.claude").expanduser()).resolve()
    if resolved == operator_home:
        raise ClaudeHomeRefused(
            f"{resolved} is the operator's own Claude home; each instance must own a "
            "private configuration directory instead"
        )
    return resolved


def resolve_config_dir(config: ClaudeProcessConfig) -> Path:
    """Return the private configuration directory, or raise.

    Re-validates rather than trusting the config object, so a config built by
    bypassing ``__post_init__`` still cannot reach the operator's home.
    """
    return _private_home(str(config.home_path))


def build_argv(config: ClaudeProcessConfig, arguments: Sequence[str] = ()) -> list[str]:
    """The child's argv: the unmodified binary plus the caller's arguments.

    No credential flag is ever appended, and no wrapper is inserted, so the
    process authenticates exactly as the official CLI would for this home.
    """
    return [config.binary, *config.extra_arguments, *arguments]


def build_environment(config: ClaudeProcessConfig, *, config_dir: Path) -> dict[str, str]:
    """Build the child environment: allowlist + ``CLAUDE_CONFIG_DIR``.

    The parent environment contributes only :data:`_INHERITED_ENV_KEYS`.  Nothing
    is read from the operator's Claude home.
    """
    source = os.environ if config.environ is None else config.environ
    env = {key: source[key] for key in _INHERITED_ENV_KEYS if source.get(key)}
    env[_FLAG] = str(config_dir)
    return env


# Probe results are cached per (binary, home) so that availability belongs to an
# instance.  A process-global "claude is available" flag is exactly the bug this
# avoids: one healthy instance would speak for every unconfigured one.
_PROBE_CACHE: dict[tuple[str, str], ClaudeProbeResult] = {}


def probe(config: ClaudeProcessConfig, *, use_cache: bool = True) -> ClaudeProbeResult:
    """Report whether this instance can spawn, keyed by binary path and home."""
    config_dir = resolve_config_dir(config)
    binary_path = shutil.which(config.binary)
    key = (binary_path or config.binary, str(config_dir))
    if use_cache and key in _PROBE_CACHE:
        return _PROBE_CACHE[key]

    if binary_path is None:
        result = ClaudeProbeResult(available=False, binary=config.binary,
                                   config_dir=str(config_dir),
                                   detail=f"{config.binary!r} is not on PATH")
        _PROBE_CACHE[key] = result
        return result

    env = build_environment(config, config_dir=config_dir)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [config.binary, "--version"],
            env=env, cwd=str(config.cwd) if config.cwd else None,
            capture_output=True, text=True, timeout=min(config.timeout_seconds, 30.0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result = ClaudeProbeResult(available=False, binary=config.binary,
                                   config_dir=str(config_dir), binary_path=binary_path,
                                   detail=f"{type(exc).__name__}: {exc}")
        _PROBE_CACHE[key] = result
        return result

    version = (completed.stdout or completed.stderr or "").strip().splitlines()
    result = ClaudeProbeResult(
        available=completed.returncode == 0,
        binary=config.binary,
        config_dir=str(config_dir),
        binary_path=binary_path,
        version=version[0] if version else "",
        detail="" if completed.returncode == 0 else f"exit {completed.returncode}",
    )
    _PROBE_CACHE[key] = result
    return result


def clear_probe_cache() -> None:
    """Drop cached probes (tests, and any caller that changes the environment)."""
    _PROBE_CACHE.clear()


def run(config: ClaudeProcessConfig, arguments: Sequence[str] = (), *,
        stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Spawn one instance and wait for it.

    The private configuration directory is created if absent, mode 0700, and is
    left empty: this seam never writes credentials, and never populates the home
    from the operator's own.
    """
    config_dir = resolve_config_dir(config)
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    argv = build_argv(config, arguments)
    env = build_environment(config, config_dir=config_dir)
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, env=env, cwd=str(config.cwd) if config.cwd else None,
            input=stdin_text, capture_output=True, text=True,
            timeout=config.timeout_seconds, check=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeBinaryUnavailable(f"{config.binary!r} not found: {exc}") from exc
