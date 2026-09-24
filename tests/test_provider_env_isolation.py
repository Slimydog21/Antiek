"""CI must blank every provider credential the dispatch code reads.

Guards against the drift that let ``XIAOMI_API_KEY`` and ``Z_AI_API_KEY`` be read
by ``substrate/dispatch`` while CI blanked only a hand-written subset. A test that
reaches dispatch with an ambient key opens a real socket to a real vendor, which
makes the suite's result depend on the machine and can spend real money.
"""
import pytest
import yaml

from tools.lint import provider_env_isolation as isolation


def test_ci_blanks_every_provider_credential():
    assert isolation.check() == []


def test_discovery_is_not_vacuous():
    """A lint that discovers nothing would pass forever. Pin the known providers."""
    found = isolation.provider_env_vars()
    assert {"ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
            "XIAOMI_API_KEY", "Z_AI_API_KEY", "HERMES_API_KEY"} <= found


def _workflow(tmp_path, env: dict | None, run: str):
    """Build a one-step workflow structurally — string indentation is too easy to get wrong."""
    step = {"name": "Run pytest shard", "run": run}
    if env is not None:
        step["env"] = env
    path = tmp_path / "ci.yml"
    path.write_text(yaml.safe_dump({"jobs": {"suite": {"steps": [step]}}}))
    return path


ALL_KEYS = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "HERMES_API_KEY", "OPENAI_API_KEY",
            "OPENROUTER_API_KEY", "XIAOMI_API_KEY", "Z_AI_API_KEY"]


@pytest.mark.parametrize("env,expect_failure", [
    ({"DEEPSEEK_API_KEY": ""}, True),                       # partial isolation -> must be total
    ({k: "" for k in ALL_KEYS}, False),                     # total isolation -> clean
])
def test_partial_isolation_fails_but_total_passes(monkeypatch, tmp_path, env, expect_failure):
    monkeypatch.setattr(isolation, "WORKFLOW", _workflow(tmp_path, env, "python -m pytest tests/ -q"))
    assert bool(isolation.check()) is expect_failure


def test_a_key_set_to_a_real_value_is_rejected(monkeypatch, tmp_path):
    """Blanking means ``""`` — pointing a job at a live key defeats the purpose."""
    env = {k: "" for k in ALL_KEYS}
    env["XIAOMI_API_KEY"] = "sk-live"
    monkeypatch.setattr(isolation, "WORKFLOW", _workflow(tmp_path, env, "python -m pytest tests/ -q"))
    assert any("non-empty" in error for error in isolation.check())


def test_a_step_that_never_opted_in_is_left_alone(monkeypatch, tmp_path):
    """The lint closes drift; it does not force isolation onto unrelated jobs."""
    monkeypatch.setattr(isolation, "WORKFLOW",
                        _workflow(tmp_path, None, "python -m pytest compounding/benchmark/tests/ -q"))
    assert isolation.check() == []


def test_full_suite_step_must_isolate_even_with_no_env_at_all(monkeypatch, tmp_path):
    """Running tests/ is the high-risk case; absence of an env block is not an excuse."""
    monkeypatch.setattr(isolation, "WORKFLOW", _workflow(tmp_path, None, "python -m pytest tests/ -q"))
    assert any("does not blank" in error for error in isolation.check())


def test_isolation_does_not_strip_non_dispatch_keys(monkeypatch):
    """`EXA_API_KEY` gates an opt-in operator test that skips at MODULE level.

    A function-scoped fixture runs after module import, so stripping that key
    would let the module decline to skip and then fail the body — which is
    exactly what a broader `*_API_KEY` sweep did to
    `tests/test_exa_gather_returns_real_chunks.py`. The isolation set is scoped
    to dispatch providers for that reason; widening it breaks opt-in tests.
    """
    assert "EXA_API_KEY" not in isolation.provider_env_vars()


def test_conftest_isolation_set_matches_the_lint(monkeypatch):
    """conftest and CI must blank the same keys, or local stops matching CI."""
    from tests.conftest import _DISPATCH_PROVIDER_KEYS

    assert set(_DISPATCH_PROVIDER_KEYS) == isolation.provider_env_vars()
