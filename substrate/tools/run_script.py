"""run_script -- execute operator-or-agent-supplied TypeScript in a deno sandbox."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import current_burn_context
from substrate.tools.adapter_map import build_import_map
from substrate.tools.run_script_preflight import preflight
from substrate.tools.sandbox import SandboxPolicy, ScriptResult

_DISABLE_ENV = "ANTIEK_DISABLE_RUN_SCRIPT"
_USAGE_MARKER_PREFIX = "__antiek_usage__:"


class RunScriptDisabled(RuntimeError):
    pass


def is_enabled() -> bool:
    return os.environ.get(_DISABLE_ENV) != "1"


def _parse_usage_marker(stdout: str) -> tuple[int, int, int, str | None]:
    in_tok = out_tok = cached_tok = 0
    model: str | None = None
    for line in reversed(stdout.splitlines()):
        if line.startswith(_USAGE_MARKER_PREFIX):
            try:
                data = json.loads(line[len(_USAGE_MARKER_PREFIX):].strip())
                in_tok = int(data.get("input_tokens", 0))
                out_tok = int(data.get("output_tokens", 0))
                cached_tok = int(data.get("cached_tokens", 0))
                model = data.get("model")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            break
    return in_tok, out_tok, cached_tok, model


def run_script(
    script: str,
    *,
    policy: SandboxPolicy | None = None,
    timeout_s: int = 30,
    import_map: dict | None = None,
    project_root: Path | None = None,
) -> ScriptResult:
    pol = policy or SandboxPolicy.deny_all()
    burn_ctx = None
    try:
        burn_ctx = current_burn_context()
    except Exception:
        pass

    if not is_enabled():
        return ScriptResult(
            exit_code=-1, stdout="",
            stderr=f"run_script disabled by {_DISABLE_ENV}=1",
            duration_ms=0, wall_timed_out=False, policy_used=pol,
        )

    pf = preflight()
    if not pf.usable:
        return ScriptResult(
            exit_code=-1, stdout="",
            stderr=f"deno preflight failed: {pf.error}",
            duration_ms=0, wall_timed_out=False, policy_used=pol,
        )

    if import_map is None and project_root is not None:
        import_map = build_import_map(project_root)

    work = Path(tempfile.mkdtemp(prefix="antiek-runscript-"))
    try:
        script_file = work / "script.ts"
        script_file.write_text(script)
        cmd = ["deno", "run", "--no-config"]
        if import_map is not None:
            map_file = work / "import-map.json"
            map_file.write_text(json.dumps(import_map))
            cmd.append(f"--import-map={map_file}")
        cmd.extend(pol.to_deno_flags())
        cmd.append(str(script_file))

        sub_env = {k: os.environ[k] for k in pol.allow_env if k in os.environ}
        deno_path = shutil.which("deno")
        if deno_path:
            sub_env["PATH"] = str(Path(deno_path).parent)

        start = time.monotonic()
        wall_timed_out = False
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=sub_env,
            cwd=str(work),
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            wall_timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                stdout, stderr = proc.communicate()
            exit_code = -signal.SIGTERM

        duration_ms = int((time.monotonic() - start) * 1000)

        if burn_ctx is not None:
            in_tok, out_tok, cached, model = _parse_usage_marker(stdout)
            recorder = BurnRecorder.for_project(burn_ctx.project_root)
            recorder.record(
                BurnEvent(
                    session_id=burn_ctx.session_id,
                    project_id=burn_ctx.project_id,
                    call_id=f"runscript-{int(time.time() * 1e6)}",
                    model=model or "n/a",
                    tool_id="run_script",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_tokens=cached,
                    error=(
                        f"wall_timed_out after {timeout_s}s"
                        if wall_timed_out
                        else (None if exit_code == 0 else f"exit_code={exit_code}")
                    ),
                    extension_ids_active=burn_ctx.extension_ids_active,
                )
            )

        return ScriptResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr,
            duration_ms=duration_ms, wall_timed_out=wall_timed_out, policy_used=pol,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
