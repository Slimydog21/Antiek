from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from tools.ops import provider_key_probe as probe


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
    body = __import__("json").loads(requests[0].content)
    assert body["model"] == "mimo-v2.5-pro"
    assert body["max_tokens"] == 8
    assert body["messages"] == [{"role": "user", "content": "Reply with OK."}]
    client.close()


def test_zai_and_deepseek_use_production_url_model_shapes(monkeypatch):
    seen = []

    def run(name):
        def respond(request):
            seen.append((name, str(request.url), __import__("json").loads(request.content)))
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
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(401, text=f"invalid auth {secret}")
    ))
    real_make_provider = probe._make_provider

    def make_provider(name, key):
        assert name == "deepseek" and key == secret
        provider = real_make_provider(name, key)
        provider._client = client
        provider._owns_client = False
        return provider

    monkeypatch.setattr(probe, "_make_provider", make_provider)
    out, err = io.StringIO(), io.StringIO()
    code = probe.main(["deepseek", "--key-file", str(_key_file(tmp_path, secret))], stdout=out, stderr=err)

    assert code == 1
    assert secret not in out.getvalue() + err.getvalue()
    assert "invalid auth" not in out.getvalue() + err.getvalue()
    client.close()


def test_key_file_is_strict_and_never_shell_sourced(tmp_path):
    path = tmp_path / "provider.env"
    path.write_text("DEEPSEEK_API_KEY=first\nOTHER=value\n", encoding="ascii")
    path.chmod(0o600)
    with pytest.raises(probe.ProbeInputError):
        probe._read_candidate_key(path, "DEEPSEEK_API_KEY")
