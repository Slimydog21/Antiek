"""Runner-seam test — the ResearchRunner drives a provider through the interface.

Proves (M6): the runner can call a ``ResearchProvider`` THROUGH the new
``make_provider_gather_loop`` seam and receive a normalized
``ResearchResult`` whose fields flow through as ``StepEvent`` labels —
without the runner's call path branching on a provider name or a raw
provider payload (INV-1 / INV-4).

The runner today uses ``BrowseLoop`` injection, not a direct
``ResearchProvider`` call. So the seam is the ``make_provider_gather_loop``
factory: it accepts a ``ResearchProvider`` and returns a ``BrowseLoop``
the runner's existing ``_run`` machinery drives unchanged. This is the
minimal additive seam — it does not touch ``start`` / ``stream`` /
``steer`` / the existing exa gather loop.

Three assertions:
1. **Normalized result flows through:** the stub's recorded
   ``ResearchResult`` fields appear in the streamed ``StepEvent``s
   (as ``field_name`` / ``field_value`` / ``citation_urls`` data).
2. **No provider NAME in the new code path:** reading the
   ``make_provider_gather_loop`` source, the literal provider names
   ``"exa"`` and ``"parallel"`` do not appear as branch keys — the loop
   never reads ``result.provider`` to decide behavior. (Provider
   identity rides as an audit label only.)
3. **No SDK import in the seam:** the runner module does not gain a
   new provider-SDK import from this seam (the one-owner lint covers
   the whole repo; this is a focused re-check on the runner path).

The stub passes the conformance harness (verified in
``test_conformance.py``), so the result it returns is a valid
normalized shape.
"""

from __future__ import annotations

import inspect

import pytest

from research.providers.conformance import conformance
from research.providers.stub import StubResearchProvider
from research.providers.types import RawRef, ResearchResult, Source
from runtime.research_runner import (
    BudgetCap,
    HostLocalRunner,
    ResearchPlan,
    RunState,
    make_provider_gather_loop,
)

# ``make_provider_gather_loop`` source path — read as text for the
# no-provider-name assertion. Resolved from the function object so the
# test stays in sync if the module moves.
_PROVIDER_LOOP_SOURCE = inspect.getsource(make_provider_gather_loop)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def events_dir(monkeypatch, tmp_path):
    import os
    ev = tmp_path / "events"
    ev.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(ev))
    return str(ev)


def _recorded_result() -> ResearchResult:
    """A conformant result the stub returns for the test sub-question."""
    return ResearchResult(
        fields={"capital": "Paris", "currency": "EUR"},
        field_citations={
            "capital": [Source(url="https://example.com/france",
                               title="France")],
            "currency": [Source(url="https://example.com/euro",
                                title="Euro")],
        },
        confidence=0.9,
        cost=0.012,
        latency=340,
        provider="stub",
        tier="basic",
        raw_ref=RawRef(handle="stub:raw:test", provider="stub"),
    )


def _plan(iid: str = "inv-seam", **kw) -> ResearchPlan:
    return ResearchPlan(
        investigation_id=iid,
        sub_question="what is the capital of France?",
        **kw,
    )


# --------------------------------------------------------------------------
# Test 1: the stub passes conformance (the seam only proves anything if
# the provider it drives is itself conformant).
# --------------------------------------------------------------------------


def test_stub_provider_is_conformant():
    provider = StubResearchProvider(
        {"what is the capital of France?": _recorded_result()}
    )
    conformance(
        provider,
        {
            "sub_question": "what is the capital of France?",
            "output_schema": {"capital": "string", "currency": "string"},
            "expected_fields": {"capital": "Paris", "currency": "EUR"},
            "expected_confidence": 0.9,
        },
    )


# --------------------------------------------------------------------------
# Test 2: the runner drives the stub through the seam and the normalized
# result flows through as StepEvents.
# --------------------------------------------------------------------------


async def test_runner_drives_provider_through_seam(events_dir):
    provider = StubResearchProvider(
        {"what is the capital of France?": _recorded_result()}
    )
    loop_fn = make_provider_gather_loop(
        provider,
        output_schema={"capital": "string", "currency": "string"},
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=events_dir, seal_on_complete=False
    )
    h = await runner.start("inv-seam", _plan())
    events = [ev async for ev in runner.stream(h)]
    await runner.join()

    # Terminal state is DONE.
    assert runner.status(h).state == RunState.DONE

    # The plan event marks the provider gather mode (a label, not a branch).
    plan_evs = [e for e in events if e.kind == "plan"]
    assert plan_evs and plan_evs[0].data.get("gather_mode") == "provider"

    # One step per non-null field, carrying the normalized field value
    # + citation URLs + confidence/tier/provider audit labels.
    step_evs = [e for e in events if e.kind == "step"]
    assert len(step_evs) == 2
    by_field = {e.data["field_name"]: e for e in step_evs}
    assert by_field["capital"].data["field_value"] == "Paris"
    assert by_field["capital"].data["citation_urls"] == [
        "https://example.com/france"
    ]
    assert by_field["currency"].data["field_value"] == "EUR"
    # Audit labels flow through but are NOT branch keys.
    assert by_field["capital"].data["confidence"] == 0.9
    assert by_field["capital"].data["tier"] == "basic"
    assert by_field["capital"].data["provider"] == "stub"
    assert by_field["capital"].data["raw_handle"] == "stub:raw:test"

    # The note carries the joined answer (for the promotion funnel).
    note_evs = [e for e in events if e.kind == "note"]
    assert note_evs
    note_text = note_evs[0].text
    assert "Paris" in note_text and "EUR" in note_text

    # Cost reconciles: the loop charged result.cost per field step.
    # (2 steps × 0.012 = 0.024 — the loop charges per emitted step.)
    # ``cost`` takes the Handle returned by ``start`` (it reads
    # ``handle.investigation_id``), not a bare id string.
    assert runner.cost(h).spent_usd == pytest.approx(0.024)


# --------------------------------------------------------------------------
# Test 3: the new code path contains no provider NAME as a branch key.
# The loop never reads ``result.provider`` to decide behavior — it only
# writes it as an audit label. (INV-4)
# --------------------------------------------------------------------------


def test_provider_gather_loop_source_has_no_provider_branch():
    """The seam source must not branch on a provider name.

    We assert the literals ``"exa"`` and ``"parallel"`` do not appear in
    the ``make_provider_gather_loop`` source as string literals that
    could be branch keys. ``result.provider`` may appear only as the
    RHS of an assignment / a kwarg value (audit label), never inside a
    conditional.

    This is the focused INV-4 proof on the seam itself; the one-owner
    lint (test_one_owner_lint.py) is the repo-wide INV-1 proof.
    """
    src = _PROVIDER_LOOP_SOURCE
    # No provider name appears as a string literal that could branch.
    # (The word may appear in docstrings/comments — we check it is not
    # used in a conditional context by asserting no `if` mentions it.)
    assert '"exa"' not in src, (
        "make_provider_gather_loop must not mention the 'exa' provider "
        "name as a literal — that would be a branch on provider identity"
    )
    assert '"parallel"' not in src, (
        "make_provider_gather_loop must not mention the 'parallel' "
        "provider name as a literal — that would be a branch on "
        "provider identity"
    )
    # No conditional reads provider identity to decide behavior. The
    # only allowed use of result.provider is as an audit label (kwarg).
    # Assert there is no `if` line containing "provider".
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("if ") and "provider" in stripped:
            pytest.fail(
                "make_provider_gather_loop branches on 'provider' — "
                f"INV-4 violation: {stripped!r}"
            )


# --------------------------------------------------------------------------
# Test 4: the NEW seam code path imports no provider SDK / adapter package.
#
# Scope is deliberately the ``make_provider_gather_loop`` function's OWN
# source — NOT the whole ``host_local`` module. The module already contains
# ``make_exa_gather_loop`` (the pre-existing, explicitly-allowlisted INV-1
# violation that ``tests/research/test_one_owner_lint.py`` documents and
# SPR-03 removes). Walking the whole module would flag that known violation
# and conflate it with this sprint's seam, which is exactly the mistake to
# avoid. The spec asks: "assert absence of 'exa'/'parallel' in the NEW code
# path you add (read it as text)." That is what this does — it parses the
# new function's AST and asserts no import of an engine SDK or of the
# ``research.providers`` adapter package (the provider is injected and
# called structurally via ``provider.answer(...)``).
# --------------------------------------------------------------------------


def test_provider_seam_imports_no_provider_sdk():
    """The new ``make_provider_gather_loop`` seam must not import an engine
    SDK or the ``research.providers`` adapter package. The provider is
    injected (typed ``object``) and called structurally — no import, no
    branch on provider identity (INV-1 on the new code path)."""
    import ast
    import inspect

    # Source of the NEW seam ONLY. The pre-existing make_exa_gather_loop
    # import of acquisition.search.exa is out of scope here (covered + allow-
    # listed by test_one_owner_lint.py; removed in SPR-03).
    src = inspect.getsource(make_provider_gather_loop)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod_name = node.module or ""
            assert not (
                mod_name.startswith("research.providers")
                or mod_name.startswith("acquisition.search.exa")
                or mod_name.startswith("acquisition.search.parallel")
            ), (
                f"make_provider_gather_loop imports {mod_name!r} — the seam "
                "must inject the provider and call it structurally, not "
                "import an engine SDK or the adapter package (INV-1)"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not (
                    alias.name.startswith("research.providers")
                    or alias.name.startswith("acquisition.search.exa")
                    or alias.name.startswith("acquisition.search.parallel")
                ), (
                    f"make_provider_gather_loop imports {alias.name!r} — "
                    "INV-1 violation: the seam must not import an engine SDK "
                    "or the adapter package"
                )
