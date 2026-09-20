"""/health's gather mode must match the loop the cascade actually builds.

Whether DRW does real retrieval or returns a contract stub was, until now,
observable only by reading an env var on the server. That mattered more than
it sounds: ``infrastructure/ansible/templates/secrets.env.j2:64`` renders

    ANTIEK_DRW_GATHER=

EMPTY — the intended ``=exa`` sits in a comment two lines above — and
``_research_loop_factory`` reads ``os.environ.get("ANTIEK_DRW_GATHER",
"stub")``, for which an empty string is not ``"exa"``. So a deployment can do
no retrieval at all while ``infrastructure/runbooks/smoke-drw-1.md:28`` states
"Prod gather: ANTIEK_DRW_GATHER=exa ... (set via ansible)" and the smoke
checklist reads green.

A reported value that is re-derived independently would just be a second
thing to drift. These tests pin ``resolved_gather_mode()`` to the branch
``_research_loop_factory`` actually takes, for every combination of the two
env vars that steer it, so the word on /health cannot become a comfortable
fiction.
"""

from __future__ import annotations

import pytest

from interfaces.research.api import cascade_routes

_GATHER = "ANTIEK_DRW_GATHER"


def _backend_env() -> str:
    return str(cascade_routes.BACKEND_ENV)


@pytest.mark.parametrize(
    ("gather", "backend", "expected"),
    [
        (None, None, "stub"),
        ("", None, "stub"),
        ("   ", None, "stub"),
        ("stub", None, "stub"),
        ("exa", None, "exa"),
        ("EXA", None, "exa"),
        (None, "local", "contained"),
        ("stub", "local", "contained"),
        ("exa", "local", "conflict"),
    ],
)
def test_reported_mode_matches_the_branch_taken(
    monkeypatch: pytest.MonkeyPatch,
    gather: str | None,
    backend: str | None,
    expected: str,
) -> None:
    monkeypatch.delenv(_GATHER, raising=False)
    monkeypatch.delenv(_backend_env(), raising=False)
    if gather is not None:
        monkeypatch.setenv(_GATHER, gather)
    if backend is not None:
        monkeypatch.setenv(_backend_env(), backend)
    assert cascade_routes.resolved_gather_mode() == expected


def test_empty_env_really_does_mean_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """The specific shape ansible renders today.

    If this ever reports "exa", the template started interpolating a value
    and the runbook's claim became true — update secrets.env.j2's comment
    rather than this test.
    """
    monkeypatch.delenv(_backend_env(), raising=False)
    monkeypatch.setenv(_GATHER, "")
    assert cascade_routes.resolved_gather_mode() == "stub"


def test_conflict_word_corresponds_to_a_real_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"conflict" must mean the factory raises, not merely that we said so."""
    monkeypatch.setenv(_GATHER, "exa")
    monkeypatch.setenv(_backend_env(), "local")
    assert cascade_routes.resolved_gather_mode() == "conflict"
    with pytest.raises(RuntimeError, match="mutually exclusive"):
        cascade_routes._research_loop_factory()


def test_health_reports_the_same_word(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    monkeypatch.delenv(_backend_env(), raising=False)
    monkeypatch.setenv(_GATHER, "exa")
    client = TestClient(create_app(register_wrestling=False))
    assert client.get("/health").json()["drw_gather_mode"] == "exa"
    assert cascade_routes.resolved_gather_mode() == "exa"
