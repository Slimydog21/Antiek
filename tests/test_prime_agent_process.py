from __future__ import annotations

import os
import shutil
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import runtime.prime_agent.process as process_module
from runtime.prime_agent.installation import (
    PrimeAgentUnavailable,
    prime_agent_artifact_digest,
    resolve_prime_agent_binary,
    verify_prime_agent_installation,
)
from runtime.prime_agent.process import (
    PrimeAgentProcessConfig,
    run_prime_agent_process,
    spawn_prime_agent_managed,
)


def _script(tmp_path: Path, body: str) -> Path:
    return _raw_script(
        tmp_path,
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n print('prime-agent 0.7.4'); raise SystemExit\n"
        "if sys.argv[1:] == ['--help']:\n print('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc'); raise SystemExit\n"
        + body,
    )


def _raw_script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "prime-agent"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path.resolve()


def _config(binary: Path, tmp_path: Path, **changes: object) -> PrimeAgentProcessConfig:
    values: dict[str, object] = {
        "installation": verify_prime_agent_installation(
            binary, environ={"PATH": os.environ["PATH"]}
        ),
        "cwd": tmp_path.resolve(),
        "timeout_seconds": 1.0,
        "max_stdout_bytes": 128,
        "max_stderr_bytes": 128,
        "environ": {"PATH": os.environ["PATH"], "HOME": "/ambient/home", "SECRET": "no"},
    }
    values.update(changes)
    return PrimeAgentProcessConfig(**values)  # type: ignore[arg-type]


def test_resolution_and_version_capability_contract(tmp_path: Path) -> None:
    binary = _raw_script(
        tmp_path,
        """import sys
if sys.argv[1:] == ['--version']: print('prime-agent 0.7.9')
elif sys.argv[1:] == ['--help']: print('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc')
""",
    )
    env = {"PATH": str(tmp_path), "ANTIEK_PRIME_AGENT_BIN": "prime-agent"}
    assert resolve_prime_agent_binary(env) == binary
    assert verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]}).version == (
        0,
        7,
        9,
    )


@pytest.mark.parametrize("version", ["0.6.9", "0.8.0", "nonsense"])
def test_version_drift_is_rejected(tmp_path: Path, version: str) -> None:
    binary = _raw_script(
        tmp_path,
        f"import sys\nprint('prime-agent {version}' if '--version' in sys.argv else '-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc')\n",
    )
    with pytest.raises(PrimeAgentUnavailable):
        verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})


def test_help_substrings_cannot_impersonate_exact_short_flag(tmp_path: Path) -> None:
    binary = _raw_script(
        tmp_path,
        "import sys\nprint('prime-agent 0.7.4' if '--version' in sys.argv else '--cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc')\n",
    )
    with pytest.raises(PrimeAgentUnavailable, match="-p"):
        verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})


def test_atomic_path_replacement_after_verification_is_refused(tmp_path: Path) -> None:
    binary = _script(tmp_path, "print('original')\n")
    config = _config(binary, tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_text(binary.read_text().replace("original", "replacement"))
    replacement.chmod(binary.stat().st_mode)
    replacement.replace(binary)

    with pytest.raises(PrimeAgentUnavailable, match="changed"):
        run_prime_agent_process(config, (), stdin=b"")


def test_fd_bound_spawn_executes_verified_script_during_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _script(tmp_path, "print('verified')\n")
    config = _config(binary, tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_text(binary.read_text().replace("verified", "hostile"))
    replacement.chmod(binary.stat().st_mode)

    def replace_after_open() -> None:
        replacement.replace(binary)

    monkeypatch.setattr(process_module, "_pre_spawn_hook", replace_after_open)
    result = run_prime_agent_process(config, (), stdin=b"")
    assert result.stdout.strip() == b"verified"


def test_prompt_is_stdin_and_environment_is_isolated(tmp_path: Path) -> None:
    binary = _script(
        tmp_path,
        "import os, sys\nprint(sys.stdin.read())\nprint(os.environ.get('SECRET'), os.environ['HOME'], file=sys.stderr)\n",
    )
    result = run_prime_agent_process(_config(binary, tmp_path), ("-p",), stdin=b"hostile $(x)")
    assert result.argv == (str(binary), "-p")
    assert "hostile" not in " ".join(result.argv)
    assert result.stdout.strip() == b"hostile $(x)"
    assert result.stderr.startswith(b"None ")
    assert b"/ambient/home" not in result.stderr


def test_timeout_kills_hostile_grandchild(tmp_path: Path) -> None:
    marker = tmp_path / "escaped"
    binary = _script(
        tmp_path,
        f"""import subprocess, sys, time
subprocess.Popen([sys.executable, '-c', "import pathlib,time;time.sleep(.4);pathlib.Path({str(marker)!r}).write_text('bad')"])
time.sleep(10)
""",
    )
    config = _config(binary, tmp_path, timeout_seconds=0.08, terminate_grace_seconds=0.03)
    started = time.monotonic()
    result = run_prime_agent_process(
        config, (), stdin=b""
    )
    assert result.timed_out
    assert time.monotonic() - started < 0.5
    time.sleep(0.5)
    assert not marker.exists()


@pytest.mark.parametrize(("fd", "field"), [(1, "stdout_limit_exceeded"), (2, "stderr_limit_exceeded")])
def test_each_output_stream_is_bounded(tmp_path: Path, fd: int, field: str) -> None:
    binary = _script(tmp_path, f"import os\nos.write({fd}, b'x' * 10000)\n")
    result = run_prime_agent_process(_config(binary, tmp_path, max_stdout_bytes=32, max_stderr_bytes=32), (), stdin=b"")
    assert getattr(result, field)
    assert len(result.stdout) <= 32
    assert len(result.stderr) <= 32


def test_managed_process_supports_bounded_line_exchange(tmp_path: Path) -> None:
    binary = _script(
        tmp_path,
        "import sys\nfor line in sys.stdin.buffer:\n sys.stderr.write('note\\n'); sys.stderr.flush(); sys.stdout.buffer.write(line); sys.stdout.buffer.flush()\n",
    )
    with spawn_prime_agent_managed(_config(binary, tmp_path), ("--mode", "rpc")) as managed:
        session_dir = managed.session_dir
        assert session_dir.is_dir()
        deadline = time.monotonic() + 1
        managed.send_line(b'{"type":"prompt"}', deadline=deadline)
        assert managed.read_line(max_bytes=64, deadline=deadline) == b'{"type":"prompt"}\n'
        managed.close_stdin()
        assert managed.wait_exit(deadline=deadline) == 0
    assert not session_dir.exists()


def test_only_allowlisted_provider_credential_is_injected(tmp_path: Path) -> None:
    binary = _script(
        tmp_path,
        "import os\nprint(os.environ.get('OPENAI_API_KEY') == 'token', os.environ.get('SECRET'))\n",
    )
    config = _config(binary, tmp_path, provider_environment={"OPENAI_API_KEY": "token"})
    result = run_prime_agent_process(config, (), stdin=b"")
    assert result.stdout.strip() == b"True None"
    assert "token" not in repr(config)
    with pytest.raises(ValueError, match="recognized provider credential"):
        _config(binary, tmp_path, provider_environment={"SECRET": "token"})


def test_staged_javascript_bundle_preserves_relative_imports(tmp_path: Path) -> None:
    if not Path("/usr/bin/env").exists() or not shutil.which("node"):
        pytest.skip("node is not installed")
    bundle = tmp_path / "dist" / "bundle"
    bundle.mkdir(parents=True)
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (bundle / "chunk.js").write_text("export default 'relative-ok';\n")
    binary = bundle / "cli.js"
    binary.write_text(
        "#!/usr/bin/env node\n"
        "import value from './chunk.js';\n"
        "if (process.argv.includes('--version')) console.log('prime-agent 0.7.4');\n"
        "else if (process.argv.includes('--help')) console.log('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc');\n"
        "else console.log(value);\n"
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    installation = verify_prime_agent_installation(
        binary.resolve(), environ={"PATH": os.environ["PATH"]}
    )
    result = run_prime_agent_process(
        PrimeAgentProcessConfig(
            installation=installation,
            cwd=tmp_path.resolve(),
            timeout_seconds=2,
            max_stdout_bytes=128,
            max_stderr_bytes=128,
            environ={"PATH": os.environ["PATH"]},
        ),
        (),
        stdin=b"",
    )
    assert result.stdout.strip() == b"relative-ok"

    (bundle / "chunk.js").write_text("export default 'replaced';\n")
    with pytest.raises(PrimeAgentUnavailable, match="bundle changed"):
        run_prime_agent_process(
            PrimeAgentProcessConfig(
                installation=installation,
                cwd=tmp_path.resolve(),
                timeout_seconds=2,
                max_stdout_bytes=128,
                max_stderr_bytes=128,
                environ={"PATH": os.environ["PATH"]},
            ),
            (),
            stdin=b"",
        )


def test_real_local_prime_bundle_harmless_probes() -> None:
    candidates = list(Path.home().glob(".nvm/versions/node/*/bin/prime-agent"))
    if not candidates:
        pytest.skip("local npm Prime Agent bundle is not installed")
    binary = candidates[-1].resolve(strict=True)
    started = time.monotonic()
    installation = verify_prime_agent_installation(
        binary, environ={"PATH": os.environ["PATH"]}
    )
    assert (0, 7, 0) <= installation.version < (0, 8, 0)
    assert time.monotonic() - started < 10
    warm_started = time.monotonic()
    warm = run_prime_agent_process(
        PrimeAgentProcessConfig(
            installation=installation,
            cwd=binary.parent,
            timeout_seconds=5,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            environ={"PATH": os.environ["PATH"]},
        ),
        ("--version",),
        stdin=b"",
    )
    assert ".".join(map(str, installation.version)).encode() in warm.stdout + warm.stderr
    assert time.monotonic() - warm_started < 5


def test_stage_cache_reuses_one_artifact_for_probes_and_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process_module._cleanup_stage_cache()
    binary = _script(tmp_path, "print('answer')\n")
    import runtime.prime_agent.installation as installation_module

    calls = 0
    original = installation_module.stage_verified_prime_agent

    def counted(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(installation_module, "stage_verified_prime_agent", counted)
    config = _config(binary, tmp_path)
    assert run_prime_agent_process(config, (), stdin=b"").stdout.strip() == b"answer"
    assert calls == 1


def test_parallel_first_use_stages_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = _script(tmp_path, "print('parallel')\n")
    config = _config(binary, tmp_path)
    process_module._cleanup_stage_cache()
    import runtime.prime_agent.installation as installation_module

    calls = 0
    original = installation_module.stage_verified_prime_agent

    def counted(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(installation_module, "stage_verified_prime_agent", counted)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: run_prime_agent_process(config, (), stdin=b"").stdout, range(4)))
    assert all(output.strip() == b"parallel" for output in outputs)
    assert calls == 1


def test_cache_tamper_is_detected_and_safely_rebuilt(tmp_path: Path) -> None:
    binary = _script(tmp_path, "print('trusted')\n")
    config = _config(binary, tmp_path)
    run_prime_agent_process(config, (), stdin=b"")
    key = prime_agent_artifact_digest(config.installation)
    staged = process_module._CACHE_GENERATIONS[key][-1].path / binary.name
    staged.chmod(0o600)
    staged.write_text("#!/usr/bin/env python3\nprint('tampered')\n")

    result = run_prime_agent_process(config, (), stdin=b"")
    assert result.stdout.strip() == b"trusted"


def test_post_snapshot_cache_replacement_cannot_change_executed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _script(tmp_path, "print('verified-snapshot')\n")
    config = _config(binary, tmp_path)
    key = prime_agent_artifact_digest(config.installation)

    def tamper_shared_generation() -> None:
        staged = process_module._CACHE_GENERATIONS[key][-1].path / binary.name
        staged.chmod(0o600)
        staged.write_text("#!/usr/bin/env python3\nprint('shared-tamper')\n")

    monkeypatch.setattr(process_module, "_pre_spawn_hook", tamper_shared_generation)
    result = run_prime_agent_process(config, (), stdin=b"")
    assert result.stdout.strip() == b"verified-snapshot"


def test_live_lazy_import_survives_shared_generation_rebuild(tmp_path: Path) -> None:
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    bundle = tmp_path / "dist" / "bundle"
    bundle.mkdir(parents=True)
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    chunk = bundle / "chunk.js"
    chunk.write_text("export default 'lazy-ok';\n")
    binary = bundle / "cli.js"
    binary.write_text(
        "#!/usr/bin/env node\n"
        "if (process.argv.includes('--version')) { console.log('prime-agent 0.7.4'); process.exit(0); }\n"
        "if (process.argv.includes('--help')) { console.log('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc'); process.exit(0); }\n"
        "console.log('ready');\n"
        "process.stdin.once('data', async () => console.log((await import('./chunk.js')).default));\n"
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    installation = verify_prime_agent_installation(binary.resolve(), environ={"PATH": os.environ["PATH"]})
    config = PrimeAgentProcessConfig(
        installation=installation,
        cwd=tmp_path.resolve(),
        timeout_seconds=2,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
        environ={"PATH": os.environ["PATH"]},
    )
    key = prime_agent_artifact_digest(installation)
    with spawn_prime_agent_managed(config, ()) as managed:
        deadline = time.monotonic() + 2
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"ready\n"
        old_generation = process_module._CACHE_GENERATIONS[key][-1]
        staged_chunk = old_generation.path / "dist" / "bundle" / "chunk.js"
        staged_chunk.chmod(0o600)
        staged_chunk.write_text("export default 'tampered';\n")
        assert run_prime_agent_process(config, ("--version",), stdin=b"").exit_code == 0
        assert old_generation.path.exists()
        managed.send_line(b"continue", deadline=deadline)
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"lazy-ok\n"
    assert not old_generation.path.exists()
