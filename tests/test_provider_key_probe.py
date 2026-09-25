from __future__ import annotations

import importlib
import io
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

probe = importlib.import_module("tools.ops.provider_key_probe")


def _key_file(tmp_path: Path, key: str = "candidate-secret") -> Path:
    path = tmp_path / "provider.env"
    path.write_text(f"DEEPSEEK_API_KEY={key}\n", encoding="ascii")
    path.chmod(0o600)
    return path


def test_probe_targets_only_selected_provider_without_router_fallback():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    probe._probe("xiaomi", "candidate-secret", client=client)

    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.mimo.xiaomi.com/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer candidate-secret"
    body = json.loads(requests[0].content)
    assert body["model"] == "mimo-v2.5-pro"
    assert body["max_tokens"] == 8
    assert body["messages"] == [{"role": "user", "content": "Reply with OK."}]
    client.close()


def test_zai_and_deepseek_use_production_url_model_shapes(monkeypatch):
    seen = []

    def run(name):
        def respond(request):
            seen.append((name, str(request.url), json.loads(request.content)))
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        probe._probe(name, "candidate-secret", client=client)
        client.close()

    run("zai")
    run("deepseek")
    assert [(name, url) for name, url, _ in seen] == [
        ("zai", "https://api.z.ai/api/paas/v4/chat/completions"),
        ("deepseek", "https://api.deepseek.com/v1/chat/completions"),
    ]
    assert seen[0][2]["model"] == "glm-5.2"
    assert seen[0][2]["thinking"] == {"type": "disabled"}
    assert seen[1][2]["model"] == "deepseek-v4-pro"


def test_malformed_key_file_never_prints_file_contents(tmp_path):
    secret = "candidate-secret"
    path = tmp_path / "provider.env"
    path.write_text(f"export DEEPSEEK_API_KEY={secret}\n", encoding="ascii")
    path.chmod(0o600)
    out, err = io.StringIO(), io.StringIO()

    code = probe.main(["deepseek", "--key-file", str(path)], stdout=out, stderr=err)

    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


def test_upstream_error_never_prints_secret_or_body(tmp_path, monkeypatch):
    secret = "candidate-secret"
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(401, text=f"invalid auth {secret}")

    real_client_type = httpx.Client

    def mock_client(*, timeout, trust_env):
        assert trust_env is False
        return real_client_type(
            timeout=timeout,
            trust_env=trust_env,
            transport=httpx.MockTransport(respond),
        )

    monkeypatch.setattr(probe.httpx, "Client", mock_client)
    out, err = io.StringIO(), io.StringIO()
    code = probe.main(["deepseek", "--key-file", str(_key_file(tmp_path, secret))], stdout=out, stderr=err)

    assert code == 1
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.deepseek.com/v1/chat/completions"
    assert requests[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in out.getvalue() + err.getvalue()
    assert "invalid auth" not in out.getvalue() + err.getvalue()


def test_key_file_is_strict_and_never_shell_sourced(tmp_path):
    path = tmp_path / "provider.env"
    path.write_text("DEEPSEEK_API_KEY=first\nOTHER=value\n", encoding="ascii")
    path.chmod(0o600)
    with pytest.raises(probe.ProbeInputError):
        probe._read_candidate_key(path, "DEEPSEEK_API_KEY")


def _pretend_root_owned_0600(monkeypatch):
    real_fstat = os.fstat

    def fstat(fd):
        actual = real_fstat(fd)
        return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0,
                               st_gid=actual.st_gid, st_size=actual.st_size)

    monkeypatch.setattr(probe.os, "fstat", fstat)


def _pretend_root_owned_mode(monkeypatch, mode, gid):
    real_fstat = os.fstat

    def fstat(fd):
        actual = real_fstat(fd)
        return SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=0,
                               st_gid=gid, st_size=actual.st_size)

    monkeypatch.setattr(probe.os, "fstat", fstat)


def test_live_env_mode_selects_only_requested_key_and_labels_source(tmp_path, monkeypatch):
    secret = "live-candidate-secret"
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        f"# service secrets\n; generated comment\nlegacy note without equals\n"
        f"OTHER_KEY=ignored\nOTHER_QUOTED='same-line value'\n"
        f"DEEPSEEK_API_KEY={secret}\nZ_AI_API_KEY=also-ignored\n",
        encoding="ascii",
    )
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    _pretend_root_owned_0600(monkeypatch)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    real_client_type = httpx.Client

    def mock_client(*, timeout, trust_env):
        assert trust_env is False
        return real_client_type(timeout=timeout, trust_env=trust_env,
                                transport=httpx.MockTransport(respond))

    monkeypatch.setattr(probe.httpx, "Client", mock_client)
    out, err = io.StringIO(), io.StringIO()
    code = probe.main(["deepseek", "--live-env"], stdout=out, stderr=err)

    assert code == 0
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == f"Bearer {secret}"
    assert "live EnvironmentFile key" in out.getvalue()
    assert "does not prove the running service loaded this value or verify BYOK state" in out.getvalue()
    assert secret not in out.getvalue() + err.getvalue()


def test_live_env_accepts_deployed_root_antiek_0640_shape(tmp_path, monkeypatch):
    env_file = tmp_path / "secrets.env"
    env_file.write_text("DEEPSEEK_API_KEY=live-secret\n", encoding="ascii")
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    antiek_gid = 421
    _pretend_root_owned_mode(monkeypatch, 0o640, antiek_gid)
    monkeypatch.setattr(probe.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=antiek_gid))

    assert probe._read_live_env_key(env_file, "DEEPSEEK_API_KEY") == "live-secret"


def test_live_env_rejects_wrong_group_for_0640_without_leaking_key(tmp_path, monkeypatch):
    secret = "private-live-secret"
    env_file = tmp_path / "secrets.env"
    env_file.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="ascii")
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    _pretend_root_owned_mode(monkeypatch, 0o640, 999)
    monkeypatch.setattr(probe.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=421))
    monkeypatch.setattr(probe, "_probe", lambda *args: pytest.fail("must not probe wrong-group file"))
    out, err = io.StringIO(), io.StringIO()

    code = probe.main(["deepseek", "--live-env"], stdout=out, stderr=err)

    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


@pytest.mark.parametrize("contents", [
    "DEEPSEEK_API_KEY=first\nDEEPSEEK_API_KEY=second\n",
    'DEEPSEEK_API_KEY="quoted-secret"\n',
    "DEEPSEEK_API_KEY=bad value\n",
    " DEEPSEEK_API_KEY=trimmed-name\n",
    "DEEPSEEK_API_KEY =spaced-name\n",
    "DEEPSEEK_API_KEY= spaced-value\n",
    "DEEPSEEK_API_KEY=spaced-value \n",
])
def test_live_env_rejects_duplicates_and_complex_keys_without_leaks(tmp_path, monkeypatch, contents):
    secret = "quoted-secret"
    env_file = tmp_path / "secrets.env"
    env_file.write_text(contents, encoding="ascii")
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    _pretend_root_owned_0600(monkeypatch)
    monkeypatch.setattr(probe, "_probe", lambda *args: pytest.fail("must not probe invalid selected value"))
    out, err = io.StringIO(), io.StringIO()

    code = probe.main(["deepseek", "--live-env"], stdout=out, stderr=err)

    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


def test_live_env_rejects_continuation_before_selected_assignment(tmp_path, monkeypatch):
    secret = "live-secret-that-must-not-be-probed"
    env_file = tmp_path / "secrets.env"
    env_file.write_text(f"UNRELATED=prefix\\\nDEEPSEEK_API_KEY={secret}\n", encoding="ascii")
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    _pretend_root_owned_0600(monkeypatch)
    monkeypatch.setattr(probe, "_probe", lambda *args: pytest.fail("continuation could capture selected key"))
    out, err = io.StringIO(), io.StringIO()

    code = probe.main(["deepseek", "--live-env"], stdout=out, stderr=err)

    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


@pytest.mark.parametrize("quote", ["'", '"'])
def test_live_env_rejects_multiline_unrelated_quote_before_selected_key(tmp_path, monkeypatch, quote):
    secret = "must-not-be-selected-from-another-variable"
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        f"OTHER={quote}first\nDEEPSEEK_API_KEY={secret}\nlast{quote}\n",
        encoding="ascii",
    )
    env_file.chmod(0o600)
    monkeypatch.setattr(probe, "_LIVE_ENV_FILE", env_file)
    _pretend_root_owned_0600(monkeypatch)
    monkeypatch.setattr(probe, "_probe", lambda *args: pytest.fail("multiline value could capture selected key"))
    out, err = io.StringIO(), io.StringIO()

    code = probe.main(["deepseek", "--live-env"], stdout=out, stderr=err)

    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


def test_noncanonical_endpoint_override_fails_before_transport_and_hides_secret(monkeypatch):
    secret = "candidate-secret"
    monkeypatch.setenv("ANTIEK_DEEPSEEK_BASE_URL", "https://attacker.invalid/v1")
    requests = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))
    with pytest.raises(probe.ProbeInputError):
        probe._probe("deepseek", secret, client=client)
    assert requests == []
    client.close()


def test_noncanonical_endpoint_override_main_output_hides_secret(tmp_path, monkeypatch):
    secret = "candidate-secret"
    monkeypatch.setenv("ANTIEK_DEEPSEEK_BASE_URL", "https://attacker.invalid/v1")
    out, err = io.StringIO(), io.StringIO()
    code = probe.main(["deepseek", "--key-file", str(_key_file(tmp_path, secret))], stdout=out, stderr=err)
    assert code == 2
    assert secret not in out.getvalue() + err.getvalue()


def test_probe_refuses_model_drift_from_dispatch_config(monkeypatch, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("tiers:\n  fast:\n    provider: deepseek\n    model: deepseek-next\n", encoding="utf-8")
    monkeypatch.setattr(probe, "_CONFIG_FILE", config)
    requests = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))

    with pytest.raises(probe.ProbeInputError, match="does not exactly match config.yaml"):
        probe._probe("deepseek", "candidate-secret", client=client)

    assert requests == []
    client.close()
