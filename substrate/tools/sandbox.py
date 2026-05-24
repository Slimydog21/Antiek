"""SandboxPolicy + ScriptResult -- capability-based sandbox configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxPolicy:
    allow_net: tuple[str, ...] = ()
    allow_read: tuple[str, ...] = ()
    allow_write: tuple[str, ...] = ()
    allow_env: tuple[str, ...] = ()
    allow_run: tuple[str, ...] = ()

    @classmethod
    def deny_all(cls) -> "SandboxPolicy":
        return cls()

    def to_deno_flags(self) -> list[str]:
        flags: list[str] = []
        if self.allow_net:
            flags.append(f"--allow-net={','.join(self.allow_net)}")
        if self.allow_read:
            flags.append(f"--allow-read={','.join(self.allow_read)}")
        if self.allow_write:
            flags.append(f"--allow-write={','.join(self.allow_write)}")
        if self.allow_env:
            flags.append(f"--allow-env={','.join(self.allow_env)}")
        if self.allow_run:
            flags.append(f"--allow-run={','.join(self.allow_run)}")
        return flags


@dataclass(frozen=True)
class ScriptResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    wall_timed_out: bool
    policy_used: SandboxPolicy

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.wall_timed_out
