"""Tests for the decomposer role extraction (Sprint 6 day 1-2).

Coverage — prompt + parser:

1. ``render_full_prompt`` substitutes placeholders + threads
   ``extra_user_prefix`` through.
2. ``parse_decomposer_response`` accepts a well-formed response.
3. ``parse_decomposer_response`` rejects bad categories,
   bad evidence types, sub-question counts outside [4, 8],
   keyword counts outside [8, 20], synonyms > 3, missing required
   fields, JSON garbage.
4. ``expected_investigation_id`` mismatch rejected.
5. Drift detection — module sets equal schema Literal sets.

Coverage — bridge:

6. End-to-end happy path: DECOMPOSE_QUESTION_REQUESTED → dispatch →
   DECOMPOSE_QUESTION_DELIVERED with the parsed sub-questions and
   keywords; paraphrase_pass_count == 1.
7. Paraphrase-flag path: stub embedder flags pass-1 → bridge emits
   DECOMPOSER_PARAPHRASE_FLAGGED → regenerates → emits
   DECOMPOSER_REGENERATED → final Delivered carries
   paraphrase_pass_count == 2.
8. Provider unavailable → fallback Delivered with empty
   decomposition + policy_id stamped ``decomposer-fallback/no-provider``.
9. Malformed-JSON path → fallback Delivered with empty decomposition.
10. Golden-trace ratchet: the synthetic-causal-xy fixture's
    decomposer role.call signature replays without raising.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from roles.decomposer import (  # noqa: E402
    DECOMPOSER_CATEGORIES,
    DECOMPOSER_EVIDENCE_TYPES,
    DECOMPOSER_SYSTEM_PROMPT,
    DecomposerValidationError,
    parse_decomposer_response,
    render_full_prompt,
    render_user_template,
)
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    DecomposeQuestionDeliveredPayload,
    DecomposerParaphraseFlaggedPayload,
    DecomposerRegeneratedPayload,
    Event,
    EvidenceTypeRequired,
    SubQuestionCategory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubDecomposer:
    """Provider returning canned text. Counter increments per call so
    the regen path can return a different response than pass 1."""

    name = "stub-decomposer"

    def __init__(self, responses: list[str], *, raise_on_call: bool = False):
        self._responses = responses
        self._raise = raise_on_call
        self.call_count = 0

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if self._raise:
            raise ProviderError(
                "stub failure", provider=self.name, model=model, latency_ms=0,
            )
        idx = min(self.call_count, len(self._responses) - 1)
        text = self._responses[idx]
        self.call_count += 1
        return RawProviderResponse(
            text=text,
            raw_usage={"input_tokens": 100, "output_tokens": 60},
            finish_reason="end_turn",
            latency_ms=5,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _decomposer_config(provider_name: str) -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    pro = TierConfig(
        name="pro", provider=provider_name, model="stub-pro-model",
        max_tokens=4096, temperature=0.1, context_budget_tokens=128_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"decomposer": "pro"},
        tiers={"pro": pro},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


@pytest.fixture
def app_and_bus():
    """create_app without an embedder is fine for tests that inject
    their own decomposer-handler-level embedder via _patch_handler."""
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _patch_embedder_into_handler(bus, embedder):
    """The handler registered at create_app() captured embedder=None.
    Replace the per-action handler list directly with a test-embedder
    variant. ``EventBroadcaster`` is append-only by design; tests reach
    into ``_handlers`` to keep the production API minimal."""
    from interfaces.research.api.decomposer import make_decomposer_handler
    bus._handlers[ActionType.DECOMPOSE_QUESTION_REQUESTED.value] = [
        make_decomposer_handler(bus, embedder=embedder),
    ]


def _well_formed_decomp() -> dict:
    """One canonical good decomposition. 4 sub_qs (min) + 8 keywords (min)."""
    return {
        "investigation_id": "inv-test",
        "decomposition": [
            {
                "sub_question": "What primary evidence shows X is real?",
                "category": "technology_risk",
                "rationale": "Independent verification is needed to defend the thesis.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What is the addressable market size for X?",
                "category": "market_sizing",
                "rationale": "Magnitude determines whether the thesis is worth pursuing.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What execution risks have manifested in comparable cases?",
                "category": "team_and_execution",
                "rationale": "Prior art bounds the credibility of execution claims.",
                "evidence_type_required": "qualitative",
            },
            {
                "sub_question": "What regulatory exposure does X face?",
                "category": "regulatory_exposure",
                "rationale": "Regulatory blocks invalidate the thesis regardless of merit.",
                "evidence_type_required": "mixed",
            },
        ],
        "keywords": [
            {"term": f"keyword_{i}", "synonyms": [f"alt_{i}"]}
            for i in range(8)
        ],
    }


def _flagged_decomp() -> dict:
    """A decomposition with a sub-question that paraphrases the
    top-level question (stub embedder will flag it)."""
    d = _well_formed_decomp()
    d["decomposition"][0]["sub_question"] = "What is X causally related to Y?"
    return d


# ---------------------------------------------------------------------------
# 1. Prompt rendering
# ---------------------------------------------------------------------------


def test_render_user_template_substitutes_placeholders():
    s = render_user_template(
        investigation_id="inv-1", question="Q?", context="C",
    )
    assert "inv-1" in s
    assert "Q?" in s
    assert "C" in s
    assert "{{investigation_id}}" not in s
    assert "{{question}}" not in s
    assert "{{context}}" not in s


def test_render_user_template_handles_empty_context():
    s = render_user_template(investigation_id="i", question="q", context="")
    assert "(none)" in s


def test_render_full_prompt_includes_system_and_user():
    p = render_full_prompt(investigation_id="i", question="q", context="c")
    assert DECOMPOSER_SYSTEM_PROMPT in p
    assert "Investigation ID: `i`" in p


def test_render_full_prompt_threads_extra_user_prefix():
    p = render_full_prompt(
        investigation_id="i", question="q", context="c",
        extra_user_prefix="REGENERATE: drop paraphrases",
    )
    user_start = p.index("REGENERATE")
    sys_end = p.index(DECOMPOSER_SYSTEM_PROMPT) + len(DECOMPOSER_SYSTEM_PROMPT)
    assert user_start > sys_end  # prefix sits in the user portion


# ---------------------------------------------------------------------------
# 2-4. Parser
# ---------------------------------------------------------------------------


def test_parser_accepts_well_formed_response():
    raw = json.dumps(_well_formed_decomp())
    out = parse_decomposer_response(raw)
    assert len(out.decomposition) == 4
    assert len(out.keywords) == 8
    assert out.decomposition[0].category == "technology_risk"


def test_parser_rejects_bad_category():
    d = _well_formed_decomp()
    d["decomposition"][0]["category"] = "not_a_real_category"
    with pytest.raises(DecomposerValidationError, match="category"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_bad_evidence_type():
    d = _well_formed_decomp()
    d["decomposition"][0]["evidence_type_required"] = "scrambled"
    with pytest.raises(DecomposerValidationError, match="evidence_type_required"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_under_minimum_subqs():
    d = _well_formed_decomp()
    d["decomposition"] = d["decomposition"][:3]  # 3 < 4
    with pytest.raises(DecomposerValidationError, match="decomposition count"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_over_maximum_subqs():
    d = _well_formed_decomp()
    extra = dict(d["decomposition"][0])
    d["decomposition"] = d["decomposition"] + [extra] * 5  # 4 + 5 = 9 > 8
    with pytest.raises(DecomposerValidationError, match="decomposition count"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_under_minimum_keywords():
    d = _well_formed_decomp()
    d["keywords"] = d["keywords"][:5]  # 5 < 8
    with pytest.raises(DecomposerValidationError, match="keywords count"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_too_many_synonyms():
    d = _well_formed_decomp()
    d["keywords"][0]["synonyms"] = ["a", "b", "c", "d"]  # 4 > 3
    with pytest.raises(DecomposerValidationError, match="synonyms length"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_missing_required_field():
    d = _well_formed_decomp()
    del d["decomposition"][0]["rationale"]
    with pytest.raises(DecomposerValidationError, match="rationale"):
        parse_decomposer_response(json.dumps(d))


def test_parser_rejects_garbage_text():
    with pytest.raises(DecomposerValidationError, match="parseable JSON"):
        parse_decomposer_response("this is not JSON at all")


def test_parser_rejects_investigation_id_mismatch():
    raw = json.dumps(_well_formed_decomp())
    with pytest.raises(DecomposerValidationError, match="investigation_id mismatch"):
        parse_decomposer_response(raw, expected_investigation_id="different-inv")


def test_parser_accepts_when_investigation_id_matches():
    raw = json.dumps(_well_formed_decomp())
    out = parse_decomposer_response(raw, expected_investigation_id="inv-test")
    assert out.investigation_id == "inv-test"


def test_parser_tolerates_absent_investigation_id_when_expected_supplied():
    # GLM-5.2 intermittently omits the echoed investigation_id even though the
    # prompt asks for it. The bridge's id is authoritative, so absence must
    # fall back to it rather than crashing the cascade. (Fails on the bug:
    # _require_str raised before the fallback existed.)
    d = _well_formed_decomp()
    del d["investigation_id"]
    out = parse_decomposer_response(
        json.dumps(d), expected_investigation_id="inv-test"
    )
    assert out.investigation_id == "inv-test"


def test_parser_rejects_absent_investigation_id_when_no_expected_supplied():
    # Without an authoritative id, an omitted field is unrecoverable: we
    # cannot guess the investigation. Guards against over-loosening the
    # fallback to "always tolerate absence".
    d = _well_formed_decomp()
    del d["investigation_id"]
    with pytest.raises(DecomposerValidationError, match="investigation_id"):
        parse_decomposer_response(json.dumps(d))


# ---------------------------------------------------------------------------
# 5. Drift detection
# ---------------------------------------------------------------------------


def test_decomposer_categories_match_schema_literal():
    import typing
    assert set(typing.get_args(SubQuestionCategory)) == DECOMPOSER_CATEGORIES


def test_decomposer_evidence_types_match_schema_literal():
    import typing
    assert set(typing.get_args(EvidenceTypeRequired)) == DECOMPOSER_EVIDENCE_TYPES


# ---------------------------------------------------------------------------
# 6. Bridge — end-to-end happy path
# ---------------------------------------------------------------------------


async def _post_decompose_request(
    ac, *, investigation_id, question, context="",
):
    payload: dict[str, Any] = {
        "action_type": "decompose.requested",
        "question": question,
        "context": context,
    }
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "payload": payload,
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


class _NeverFlagsEmbedder:
    """Returns vectors orthogonal to the top-level question. The
    question (the first encode call) maps to [1, 0, 0]; everything
    else maps to [0, 1, 0]. Cosine = 0 < threshold for every
    sub-question, so the paraphrase check passes cleanly."""

    dimension = 3

    def __init__(self):
        self._seen = 0

    def encode(self, text: str) -> list[float]:
        self._seen += 1
        # First call is the top-level question; subsequent calls are
        # sub-questions. The test passes the embedder fresh per run.
        return [1.0, 0.0, 0.0] if self._seen == 1 else [0.0, 1.0, 0.0]


class _AlwaysFlagsEmbedder:
    """All texts get the same vector → cosine 1.0 with question."""

    dimension = 3

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_decomposer_happy_path_emits_delivered(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-test"

    well_formed = _well_formed_decomp()
    register_provider(_StubDecomposer([json.dumps(well_formed)]))
    _patch_dispatch_config(monkeypatch, _decomposer_config("stub-decomposer"))
    _patch_embedder_into_handler(bus, _NeverFlagsEmbedder())

    await _post_decompose_request(
        async_client, investigation_id=inv,
        question="Is X causally related to Y?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSE_QUESTION_DELIVERED.value
    ]
    assert len(delivered) == 1
    ev = Event.model_validate(delivered[0])
    assert isinstance(ev.payload, DecomposeQuestionDeliveredPayload)
    p = ev.payload
    assert len(p.decomposition) == 4
    assert len(p.keywords) == 8
    assert p.paraphrase_pass_count == 1
    assert p.paraphrase_flagged_count_final == 0
    assert ev.role == "decomposer"
    assert ev.policy_id == "stub-decomposer/stub-pro-model"

    # No paraphrase telemetry emitted on the clean path.
    flagged = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSER_PARAPHRASE_FLAGGED.value
    ]
    assert flagged == []


# ---------------------------------------------------------------------------
# 7. Bridge — paraphrase-flag → regen → delivered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_paraphrase_flag_triggers_regen(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-test"

    pass_1 = _flagged_decomp()
    pass_2 = _well_formed_decomp()
    register_provider(_StubDecomposer([json.dumps(pass_1), json.dumps(pass_2)]))
    _patch_dispatch_config(monkeypatch, _decomposer_config("stub-decomposer"))
    _patch_embedder_into_handler(bus, _AlwaysFlagsEmbedder())

    await _post_decompose_request(
        async_client, investigation_id=inv,
        question="Is X causally related to Y?",
    )
    await bus.wait_for_handlers(timeout=5.0)

    flagged = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSER_PARAPHRASE_FLAGGED.value
    ]
    assert len(flagged) == 1
    fp = Event.model_validate(flagged[0]).payload
    assert isinstance(fp, DecomposerParaphraseFlaggedPayload)
    assert fp.pass_index == 1
    assert len(fp.flagged) > 0

    regen = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSER_REGENERATED.value
    ]
    assert len(regen) == 1
    rp = Event.model_validate(regen[0]).payload
    assert isinstance(rp, DecomposerRegeneratedPayload)
    # AlwaysFlags embedder flags pass-2 too; bridge proceeds anyway.
    assert rp.still_flagged is True

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSE_QUESTION_DELIVERED.value
    ]
    assert len(delivered) == 1
    dp = Event.model_validate(delivered[0]).payload
    assert isinstance(dp, DecomposeQuestionDeliveredPayload)
    assert dp.paraphrase_pass_count == 2
    assert dp.paraphrase_flagged_count_final >= 1


# ---------------------------------------------------------------------------
# 8. Bridge — provider unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_provider_unavailable_falls_back(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-test"

    # No provider registered.
    _patch_dispatch_config(monkeypatch, _decomposer_config("stub-decomposer"))
    _patch_embedder_into_handler(bus, _NeverFlagsEmbedder())

    await _post_decompose_request(
        async_client, investigation_id=inv, question="anything",
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSE_QUESTION_DELIVERED.value
    ]
    assert len(delivered) == 1
    ev = Event.model_validate(delivered[0])
    p = ev.payload
    assert isinstance(p, DecomposeQuestionDeliveredPayload)
    assert p.decomposition == []
    assert p.keywords == []
    assert ev.policy_id == "decomposer-fallback/no-provider"


# ---------------------------------------------------------------------------
# 9. Bridge — malformed JSON fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_parse_failure_falls_back(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-test"

    register_provider(_StubDecomposer(["this is total prose, no JSON"]))
    _patch_dispatch_config(monkeypatch, _decomposer_config("stub-decomposer"))
    _patch_embedder_into_handler(bus, _NeverFlagsEmbedder())

    await _post_decompose_request(
        async_client, investigation_id=inv, question="anything",
    )
    await bus.wait_for_handlers(timeout=5.0)

    delivered = [
        r for r in trajectory(inv)
        if r["action_type"] == ActionType.DECOMPOSE_QUESTION_DELIVERED.value
    ]
    assert len(delivered) == 1
    p = Event.model_validate(delivered[0]).payload
    assert p.decomposition == []
    assert p.keywords == []


# ---------------------------------------------------------------------------
# 10. Golden-trace ratchet (synthetic-causal-xy)
# ---------------------------------------------------------------------------


def test_synthetic_golden_trace_decomposer_signature_replays():
    """Ratchet against the synthetic-causal-xy fixture. Validates only
    that the decomposer role.call signature (input_hash) is stable and
    reproducible — the synthetic fixture's output shape predates the
    typed decomposer payload so we don't assert on output_hash."""
    from tools.golden_traces.schema import GoldenTrace, stable_json_hash

    fixture_path = os.path.join(
        os.path.dirname(_HERE),
        "tools", "golden_traces", "captured", "synthetic-causal-xy.json",
    )
    with open(fixture_path) as f:
        trace = GoldenTrace.model_validate(json.load(f))

    decomp_calls = [c for c in trace.role_calls if c.role == "decomposer"]
    assert len(decomp_calls) == 1
    c = decomp_calls[0]
    assert c.input_json is not None
    # input_hash must be a stable function of input_json — replay this
    # locally and require equality with what the fixture recorded.
    replay_hash = stable_json_hash(c.input_json)
    assert replay_hash == c.input_hash
