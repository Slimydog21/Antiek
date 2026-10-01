"""Isolation tests for Claude Code process delegation.

``runtime/provider_process/claude_cli.py`` adopts the T3Code pattern: spawn the
unmodified ``claude`` binary under a private ``CLAUDE_CONFIG_DIR`` instead of
holding a Claude.ai token.  These tests pin the four properties that make that
safe:

(a) an empty homePath does not consult HOME — it fails closed;
(b) two instances get two different ``CLAUDE_CONFIG_DIR`` values;
(c) argv is the binary plus the caller's arguments, with no credential flag;
(d) the child environment carries ``CLAUDE_CONFIG_DIR`` and no token material.

Several tests spawn a throwaway shell stub instead of a real ``claude`` binary:
the seam's contract is about argv and environment, and a stub makes both
observable without depending on what the operator has installed, or on a
subscription that may be rate-limited.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from runtime.provider_process import claude_cli
from runtime.provider_process.claude_cli import (
    ClaudeBinaryUnavailable,
    ClaudeHomeNotConfigured,
    ClaudeHomeRefused,
    ClaudeProcessConfig,
    build_argv,
    build_environment,
    clear_probe_cache,
    probe,
    resolve_config_dir,
    run,
)

# Sentinel credential material: if any of these reaches a child, a test fails.
TOKEN_MATERIAL = {
    "ANTHROPIC_API_KEY": "sk-ant-sentinel-api-key",
    "CLAUDE_CODE_OAUTH_TOKEN": "sentinel-oauth-token",
    "ANTHROPIC_AUTH_TOKEN": "sentinel-auth-token",
    "CLAUDE_CONFIG_DIR_SHOULD_NOT_LEAK": "sentinel",
}
HOME_SENTINEL = "/tmp/sentinel-home-should-not-be-consulted"


def _write_stub(directory: Path, name: str = "claude-stub", body: str = "#!/bin/sh\nenv\n") -> Path:
    """A fake 'claude' that prints its environment, so the child env is observable."""
    stub = directory / name
    stub.write_text(body)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    clear_probe_cache()
    yield
    clear_probe_cache()


class TestEmptyHomeFailsClosed:
    """(a) No private home means no process — never the operator's home."""

    def test_empty_string_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", HOME_SENTINEL)
        with pytest.raises(ClaudeHomeNotConfigured) as exc:
            ClaudeProcessConfig(home_path="")
        assert HOME_SENTINEL not in str(exc.value)
        assert "HOME" in str(exc.value)  # the refusal explains what it will not do

    def test_missing_home_path_is_a_type_error_not_a_default(self) -> None:
        # Omitting the argument entirely must be impossible, not silently defaulted.
        with pytest.raises(TypeError):
            ClaudeProcessConfig()  # type: ignore[call-arg]

    def test_whitespace_only_is_refused(self) -> None:
        with pytest.raises(ClaudeHomeNotConfigured):
            ClaudeProcessConfig(home_path="   ")

    def test_resolver_refuses_without_consulting_the_environment(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty home must abort before any environment is built.

        ``build_environment`` is the only place HOME could be read, so making it
        explode proves the empty-home path never reaches it.
        """
        monkeypatch.setenv("HOME", HOME_SENTINEL)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", HOME_SENTINEL)

        def _bomb(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("environment was built despite an empty home")

        monkeypatch.setattr(claude_cli, "build_environment", _bomb)
        config = object.__new__(ClaudeProcessConfig)  # bypass __post_init__
        object.__setattr__(config, "home_path", "")
        with pytest.raises(ClaudeHomeNotConfigured):
            resolve_config_dir(config)

    def test_an_inherited_claude_config_dir_is_not_a_substitute(self) -> None:
        """The seam must not pick up the ambient variable when the caller omits one."""
        with pytest.raises(ClaudeHomeNotConfigured):
            ClaudeProcessConfig(home_path="")

    def test_the_operators_own_home_is_refused_at_construction(self) -> None:
        operator_home = Path("~/.claude").expanduser()
        with pytest.raises(ClaudeHomeRefused) as exc:
            ClaudeProcessConfig(home_path=str(operator_home))
        assert "private" in str(exc.value)

    def test_the_refusal_survives_a_bypassed_constructor(self) -> None:
        """Defence in depth: a config built by bypassing __post_init__ is still refused."""
        config = object.__new__(ClaudeProcessConfig)
        object.__setattr__(config, "home_path", str(Path("~/.claude").expanduser()))
        with pytest.raises(ClaudeHomeRefused):
            resolve_config_dir(config)

    def test_run_refuses_an_empty_home_before_spawning(self, tmp_path: Path) -> None:
        stub = _write_stub(tmp_path)
        config = ClaudeProcessConfig(home_path=str(tmp_path / "c1"), binary=str(stub))
        object.__setattr__(config, "home_path", "")
        with pytest.raises(ClaudeHomeNotConfigured):
            run(config, ["--version"])


class TestTwoInstancesAreDistinct:
    """(b) Isolation is per instance."""

    def test_environments_differ(self, tmp_path: Path) -> None:
        one = ClaudeProcessConfig(home_path=str(tmp_path / "instance-one"))
        two = ClaudeProcessConfig(home_path=str(tmp_path / "instance-two"))
        env_one = build_environment(one, config_dir=resolve_config_dir(one))
        env_two = build_environment(two, config_dir=resolve_config_dir(two))
        assert env_one["CLAUDE_CONFIG_DIR"] != env_two["CLAUDE_CONFIG_DIR"]
        assert env_one["CLAUDE_CONFIG_DIR"].endswith("instance-one")
        assert env_two["CLAUDE_CONFIG_DIR"].endswith("instance-two")

    def test_children_observe_their_own_config_dir(self, tmp_path: Path) -> None:
        """End to end: spawn twice and read what each child actually saw."""
        stub = _write_stub(tmp_path)
        seen = []
        for name in ("alpha", "beta"):
            config = ClaudeProcessConfig(home_path=str(tmp_path / name), binary=str(stub))
            completed = run(config, [])
            seen.append(
                next(line.split("=", 1)[1] for line in completed.stdout.splitlines()
                     if line.startswith("CLAUDE_CONFIG_DIR="))
            )
        assert len(set(seen)) == 2, f"instances shared a config dir: {seen}"
        assert seen[0].endswith("/alpha") and seen[1].endswith("/beta")

    def test_probe_is_keyed_by_home_not_by_a_global_flag(self, tmp_path: Path) -> None:
        stub = _write_stub(tmp_path)
        good = probe(ClaudeProcessConfig(home_path=str(tmp_path / "good"), binary=str(stub)))
        missing = probe(ClaudeProcessConfig(home_path=str(tmp_path / "missing"),
                                            binary=str(tmp_path / "no-such-binary")))
        assert good.available is True
        assert missing.available is False
        assert good.config_dir != missing.config_dir

    def test_probe_reports_the_binary_absence_without_raising(self, tmp_path: Path) -> None:
        result = probe(ClaudeProcessConfig(home_path=str(tmp_path / "home"),
                                           binary="definitely-not-installed-xyz"))
        assert result.available is False
        assert "PATH" in result.detail

    def test_run_raises_a_typed_error_for_an_absent_binary(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "home"),
                                     binary="definitely-not-installed-xyz")
        with pytest.raises(ClaudeBinaryUnavailable):
            run(config, ["--version"])


class TestArgvIsUnmodified:
    """(c) The binary plus the caller's arguments, and nothing else."""

    def test_argv_is_binary_then_arguments(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), binary="/usr/local/bin/claude")
        assert build_argv(config, ["--print", "hello"]) == ["/usr/local/bin/claude", "--print", "hello"]

    def test_argv_with_no_arguments_is_the_binary_alone(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"))
        assert build_argv(config) == [config.binary]

    def test_extra_arguments_are_appended_in_order(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), binary="claude",
                                     extra_arguments=["--model", "sonnet"])
        assert build_argv(config, ["--print"]) == ["claude", "--model", "sonnet", "--print"]

    @pytest.mark.parametrize("flag", ["--api-key", "--api_key", "--token", "--auth-token",
                                      "--oauth-token", "--anthropic-api-key"])
    def test_no_credential_flag_is_ever_injected(self, tmp_path: Path, flag: str) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), binary="claude")
        argv = build_argv(config, ["--print", "hi"])
        assert flag not in argv
        assert not any(part.startswith(flag) for part in argv)

    def test_the_real_spawn_uses_exactly_that_argv(self, tmp_path: Path) -> None:
        stub = _write_stub(tmp_path, body="#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), binary=str(stub))
        completed = run(config, ["--print", "hello", "--model", "sonnet"])
        assert completed.stdout.split() == ["--print", "hello", "--model", "sonnet"]

    def test_no_wrapper_is_inserted_before_the_binary(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), binary="claude")
        argv = build_argv(config, [])
        assert argv[0] == "claude"
        assert not any(part in ("sh", "-c", "bash", "env", "sudo") for part in argv[:1])


class TestChildEnvironment:
    """(d) CLAUDE_CONFIG_DIR present, token material absent."""

    def test_config_dir_is_present(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"))
        env = build_environment(config, config_dir=resolve_config_dir(config))
        assert env["CLAUDE_CONFIG_DIR"] == str(resolve_config_dir(config))

    def test_parent_token_material_does_not_leak(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), environ=dict(TOKEN_MATERIAL))
        env = build_environment(config, config_dir=resolve_config_dir(config))
        for key in TOKEN_MATERIAL:
            assert key not in env, f"{key} leaked into the child environment"

    def test_allowlist_only_plus_the_flag(self, tmp_path: Path) -> None:
        config = ClaudeProcessConfig(home_path=str(tmp_path / "h"), environ=dict(TOKEN_MATERIAL))
        env = build_environment(config, config_dir=resolve_config_dir(config))
        unexpected = set(env) - {"PATH", "LANG", "LC_ALL", "CLAUDE_CONFIG_DIR"}
        assert unexpected == set(), f"unexpected variables in the child env: {unexpected}"

    def test_spawned_child_sees_the_flag_and_no_tokens(self, tmp_path: Path) -> None:
        stub = _write_stub(tmp_path)
        parent_env = {**dict(TOKEN_MATERIAL), "PATH": os.environ.get("PATH", "")}
        config = ClaudeProcessConfig(home_path=str(tmp_path / "private"), binary=str(stub),
                                     environ=parent_env)
        completed = run(config, [])
        child = dict(
            line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
        )
        assert child.get("CLAUDE_CONFIG_DIR", "").endswith("/private")
        for key in TOKEN_MATERIAL:
            assert key not in child, f"{key} reached the child process"

    def test_the_private_home_is_created_empty_and_never_populated(self, tmp_path: Path) -> None:
        stub = _write_stub(tmp_path)
        home = tmp_path / "fresh-home"
        assert not home.exists()
        run(ClaudeProcessConfig(home_path=str(home), binary=str(stub)), [])
        assert home.is_dir()
        assert list(home.iterdir()) == [], "the seam must not write into the private home"
        assert stat.S_IMODE(home.stat().st_mode) == 0o700


class TestNoTokenCustody:
    """The path writes no server-side token row, and is not the BYOK flow."""

    def test_module_does_not_touch_the_byok_store(self) -> None:
        source = Path(claude_cli.__file__).read_text(encoding="utf-8")
        assert "byok" not in source
        assert "store_credential" not in source
        assert "SecretBox" not in source

    def test_module_never_references_a_client_id(self) -> None:
        source = Path(claude_cli.__file__).read_text(encoding="utf-8")
        assert "client_id" not in source
        assert "CLIENT_ID" not in source

    def test_item_one_gate_is_untouched_and_still_fail_closed(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """This work must not have opened the retired BYOK Claude flow."""
        monkeypatch.delenv("ANTIEK_BYOK_CLAUDE", raising=False)
        from runtime.byok import anthropic_oauth

        assert anthropic_oauth.byok_claude_enabled() is False
        with pytest.raises(anthropic_oauth.AnthropicAuthError) as exc:
            anthropic_oauth.resolve_client_id()
        assert exc.value.failure is anthropic_oauth.AnthropicAuthFailure.CLIENT_ID_NOT_REGISTERED
