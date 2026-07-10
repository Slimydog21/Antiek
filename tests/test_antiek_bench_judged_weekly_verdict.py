from __future__ import annotations

import ast
import hashlib
import hmac
import inspect
import json
from dataclasses import replace
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_antiek_bench_weekly_verdict import journals, suite

from substrate.antiek_bench.judged import (
    EvidenceRecord,
    PrivateJoinEnvelope,
    PrivateResponseBinding,
    VerdictPolicy,
    rubric_for,
)
from substrate.antiek_bench.live import (
    JudgedCandidateJoin,
    JudgedItemJoin,
    JudgedJoinManifest,
    build_weekly_verdict,
    deterministic_call_id,
    judged_join_mapping_digest,
    project_weekly_verdict_html,
)
from substrate.antiek_bench.live import weekly_verdict as weekly_module


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


SIGNING_KEY = b"weekly-judged-private-join-key-32-bytes-minimum"


def _sealed_envelope(item: JudgedItemJoin, row: EvidenceRecord) -> PrivateJoinEnvelope:
    by_hash = {candidate.candidate_hash: candidate for candidate in item.candidates}
    bindings = tuple(
        PrivateResponseBinding(
            label,
            by_hash[candidate_hash].live_call_id,
            by_hash[candidate_hash].provider_id,
            by_hash[candidate_hash].model_id,
            by_hash[candidate_hash].live_response_hash,
            candidate_hash,
        )
        for label, candidate_hash in zip(("A", "B"), row.candidate_hashes, strict=True)
    )
    envelope = PrivateJoinEnvelope(
        week_id=row.week_id,
        suite_version=row.suite_version,
        item_id=item.live_item_id,
        task_class=row.task_class,
        prompt_hash=item.live_prompt_hash,
        evidence_id=row.evidence_id,
        evidence_item_id_hash=row.item_id_hash,
        judge_model=row.judge_model,
        rubric_fingerprint=row.rubric_fingerprint,
        judge_policy_version="blinded-pair-v1",
        bindings=bindings,  # type: ignore[arg-type]
    )
    signature = hmac.new(SIGNING_KEY, envelope.signing_payload(), hashlib.sha256).hexdigest()
    return replace(envelope, signature="hmac-sha256:" + signature)


def _manifest() -> JudgedJoinManifest:
    base_items = tuple(
            JudgedItemJoin(
                task_class=item.task_class,
                live_item_id=item.item_id,
                live_prompt_hash=_hash(item.prompt),
                item_id_hash=_hash("salt:item:" + item.item_id),
                candidates=(
                    JudgedCandidateJoin(
                        "model-a",
                        "provider-a",
                        deterministic_call_id(
                            "wedge", "2026-W28", "live-suite-v1", "provider-a",
                            "model-a", item.task_class, item.item_id, _hash(item.prompt),
                        ),
                        hashlib.sha256(f"response:model-a:{item.item_id}".encode()).hexdigest(),
                        "A",
                        _hash("salt:a:" + item.item_id),
                    ),
                    JudgedCandidateJoin(
                        "model-b",
                        "provider-b",
                        deterministic_call_id(
                            "wedge", "2026-W28", "live-suite-v1", "provider-b",
                            "model-b", item.task_class, item.item_id, _hash(item.prompt),
                        ),
                        hashlib.sha256(f"response:model-b:{item.item_id}".encode()).hexdigest(),
                        "B",
                        _hash("salt:b:" + item.item_id),
                    ),
                ),
                rubric_version=rubric_for(item.task_class).version,
                rubric_fingerprint=rubric_for(item.task_class).fingerprint,
                task_context_hash=_hash("task-context:" + item.item_id),
                allowed_judges=("judge-1",),
                evidence_ids=(),
                position_swaps=(),
                private_envelopes=(),
            )
            for item in suite().items
        )
    rows = _evidence_for_items(base_items)
    items = tuple(
        replace(
            item,
            evidence_ids=tuple(row.evidence_id for row in rows if row.item_id_hash == item.item_id_hash),
            position_swaps=(
                tuple(row.evidence_id for row in rows if row.item_id_hash == item.item_id_hash),
            ),
            private_envelopes=tuple(
                _sealed_envelope(item, row)
                for row in rows
                if row.item_id_hash == item.item_id_hash
            ),
        )
        for item in base_items
    )
    policy = "blinded-pair-v1"
    return JudgedJoinManifest(
        week_id="2026-W28",
        suite_version="live-suite-v1",
        blinding_policy_version=policy,
        items=items,
        mapping_digest=judged_join_mapping_digest(
            "2026-W28", "live-suite-v1", policy, items
        ),
    )


def _evidence_for_items(items: tuple[JudgedItemJoin, ...]) -> tuple[EvidenceRecord, ...]:
    rows: list[EvidenceRecord] = []
    for item in items:
        axes = rubric_for(item.task_class).axes
        pair = tuple(candidate.candidate_hash for candidate in item.candidates)
        for candidate_hashes, score in ((pair, 5), (tuple(reversed(pair)), 1)):
            rows.append(
                EvidenceRecord(
                    week_id="2026-W28",
                    suite_version="live-suite-v1",
                    item_id_hash=item.item_id_hash,
                    task_class=item.task_class,  # type: ignore[arg-type]
                    rubric_version=item.rubric_version,
                    judge_model="judge-1",
                    candidate_hashes=candidate_hashes,  # type: ignore[arg-type]
                    task_context_hash=item.task_context_hash,
                    rubric_fingerprint=item.rubric_fingerprint,
                    blinded_order=("A", "B"),
                    status="ok",
                    claimed_at_ms=1,
                    scores=tuple((axis, score) for axis in axes),
                    evidence_refs=tuple((axis, ("A:fact",)) for axis in axes),
                )
            )
    return tuple(rows)


def _evidence(manifest: JudgedJoinManifest) -> tuple[EvidenceRecord, ...]:
    return _evidence_for_items(manifest.items)


def _with_items(
    manifest: JudgedJoinManifest, items: tuple[JudgedItemJoin, ...]
) -> JudgedJoinManifest:
    return replace(
        manifest,
        items=items,
        mapping_digest=judged_join_mapping_digest(
            manifest.week_id,
            manifest.suite_version,
            manifest.blinding_policy_version,
            items,
        ),
    )


def _build(
    tmp_path: Path, *, manifest=None, evidence=(), cap="1", signing_key=SIGNING_KEY
):  # type: ignore[no-untyped-def]
    calls, shadows = journals(tmp_path)
    return build_weekly_verdict(
        week_id="2026-W28",
        wedge_id="wedge",
        suite=suite(),
        call_journal=calls,
        shadow_journal=shadows,
        operator_driver="model-a",
        budget_cap_usd=Decimal(cap),
        judged_manifest=manifest,
        judged_records=evidence,
        judged_policy=VerdictPolicy("policy-v1", 1, 1, "human", "human"),
        judged_join_signing_key=signing_key,
    )


def test_exact_manifest_accepts_raw_ab_and_ba_and_keeps_layers_separate(tmp_path: Path) -> None:
    manifest = _manifest()
    verdict = _build(tmp_path, manifest=manifest, evidence=_evidence(manifest))
    assert all(task.judged and task.judged.status == "MEASURED" for task in verdict.task_verdicts)
    assert all(task.judged and task.judged.sample_size == 4 for task in verdict.task_verdicts)
    assert all(
        task.judged and "cross_item_winner_disagreement" not in task.judged.suppression_reasons
        for task in verdict.task_verdicts
    )
    assert verdict.schema_version == 2
    assert verdict.auto_promotion is False
    assert verdict.operator_acknowledgment_required is True
    payload = verdict.to_dict()
    assert "composite" not in json.dumps(payload).lower()


def test_legacy_payload_shape_and_schema_remain_v1(tmp_path: Path) -> None:
    verdict = _build(tmp_path)
    payload = verdict.to_dict()
    assert payload["schema_version"] == 1
    assert "judged_manifest_digest" not in payload
    assert "operator_acknowledgment_required" not in payload
    assert all("judged" not in task for task in payload["task_verdicts"])


def test_manifest_rejects_duplicate_judged_item_hashes() -> None:
    manifest = _manifest()
    first, second = manifest.items[:2]
    with pytest.raises(ValueError, match="item hashes must be unique"):
        replace(
            manifest,
            items=(first, replace(second, item_id_hash=first.item_id_hash), *manifest.items[2:]),
        )


def test_foreign_same_id_record_is_not_published(tmp_path: Path) -> None:
    manifest = _manifest()
    rows = list(_evidence(manifest))
    foreign = replace(rows[0], task_class="synthesize")
    assert foreign.evidence_id == rows[0].evidence_id
    verdict = _build(tmp_path, manifest=manifest, evidence=(*rows, foreign))
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "MEASURED"
    assert layer.sample_size == layer.expected_sample_size == 4


@pytest.mark.parametrize("forgery", ["task", "item", "order", "rubric", "judge"])
def test_forged_evidence_is_not_joined(tmp_path: Path, forgery: str) -> None:
    manifest = _manifest()
    rows = list(_evidence(manifest))
    row = rows[0]
    if forgery == "task":
        row = replace(row, task_class="synthesize")
    elif forgery == "item":
        row = replace(row, item_id_hash=_hash("forged-item"))
    elif forgery == "order":
        row = replace(row, candidate_hashes=(row.candidate_hashes[0], _hash("forged")))
    elif forgery == "rubric":
        row = replace(row, rubric_version="forged-rubric")
    else:
        row = replace(row, judge_model="forged-judge")
    rows[0] = row
    verdict = _build(tmp_path, manifest=manifest, evidence=rows)
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"


def test_forged_live_response_binding_is_not_joined(tmp_path: Path) -> None:
    manifest = _manifest()
    first = manifest.items[0]
    forged_candidate = replace(first.candidates[0], live_response_hash="forged-response")
    forged = _with_items(
        manifest,
        (replace(first, candidates=(forged_candidate, first.candidates[1])), *manifest.items[1:]),
    )
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest))
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"
    assert "manifest_live_join_mismatch" in layer.suppression_reasons


@pytest.mark.parametrize(
    "forgery",
    ["prompt", "provider", "call", "context", "fingerprint", "panel"],
)
def test_forged_private_join_envelope_is_not_measured(
    tmp_path: Path, forgery: str
) -> None:
    manifest = _manifest()
    first = manifest.items[0]
    if forgery == "prompt":
        changed = replace(first, live_prompt_hash=_hash("forged-prompt"))
    elif forgery in {"provider", "call"}:
        candidate = replace(
            first.candidates[0],
            **({"provider_id": "forged-provider"} if forgery == "provider" else {"live_call_id": "lc_forged"}),
        )
        changed = replace(first, candidates=(candidate, first.candidates[1]))
    elif forgery == "context":
        changed = replace(first, task_context_hash=_hash("forged-context"))
    elif forgery == "fingerprint":
        changed = replace(first, rubric_fingerprint=_hash("forged-rubric"))
    else:
        changed = replace(first, allowed_judges=("forged-judge",))
    forged = _with_items(manifest, (changed, *manifest.items[1:]))
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest))
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"


def test_manifest_rejects_forged_mapping_digest() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="mapping digest"):
        replace(manifest, mapping_digest=_hash("forged-mapping"))


def test_noncanonical_blinding_policy_is_not_measured(tmp_path: Path) -> None:
    manifest = _manifest()
    policy = "forged-policy-v9"
    forged = replace(
        manifest,
        blinding_policy_version=policy,
        mapping_digest=judged_join_mapping_digest(
            manifest.week_id, manifest.suite_version, policy, manifest.items
        ),
    )
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest))
    assert all(
        task.judged
        and task.judged.status == "NOT MEASURED"
        and "blinding_policy_mismatch" in task.judged.suppression_reasons
        for task in verdict.task_verdicts
    )


def test_forged_private_envelope_signature_is_not_measured(tmp_path: Path) -> None:
    manifest = _manifest()
    first = manifest.items[0]
    envelopes = (
        replace(first.private_envelopes[0], signature="hmac-sha256:" + "0" * 64),
        *first.private_envelopes[1:],
    )
    forged = _with_items(
        manifest,
        (replace(first, private_envelopes=envelopes), *manifest.items[1:]),
    )
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest))
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"
    assert "invalid_private_join_envelope" in layer.suppression_reasons


def test_missing_private_join_key_is_not_measured(tmp_path: Path) -> None:
    manifest = _manifest()
    verdict = _build(
        tmp_path, manifest=manifest, evidence=_evidence(manifest), signing_key=None
    )
    assert all(
        task.judged
        and task.judged.status == "NOT MEASURED"
        and "missing_private_join_key" in task.judged.suppression_reasons
        for task in verdict.task_verdicts
    )


def test_manifest_rejects_reordered_blinded_labels() -> None:
    manifest = _manifest()
    first = manifest.items[0]
    with pytest.raises(ValueError, match="invalid judged manifest item"):
        _with_items(
            manifest,
            (replace(first, candidates=tuple(reversed(first.candidates))), *manifest.items[1:]),
        )


def test_cross_item_winner_disagreement_is_explicitly_suppressed(tmp_path: Path) -> None:
    manifest = _manifest()
    rows = list(_evidence(manifest))
    second_item_hash = manifest.items[1].item_id_hash
    for index, row in enumerate(rows):
        if row.item_id_hash == second_item_hash:
            flipped = 1 if row.candidate_hashes[0] == manifest.items[1].candidates[0].candidate_hash else 5
            rows[index] = replace(row, scores=tuple((axis, flipped) for axis, _ in row.scores))
    verdict = _build(tmp_path, manifest=manifest, evidence=rows)
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.winner is None
    assert "cross_item_winner_disagreement" in layer.suppression_reasons


def test_forged_model_mixed_version_incomplete_panel_and_over_budget_suppress(tmp_path: Path) -> None:
    manifest = _manifest()
    first = manifest.items[0]
    forged = _with_items(
        manifest,
        (
            replace(
                first,
                candidates=(
                    replace(
                        first.candidates[0],
                        model_id="forged-model",
                        live_response_hash="forged-response",
                        candidate_hash=_hash("forged"),
                    ),
                    first.candidates[1],
                ),
                rubric_version="mixed-v0",
            ),
            *manifest.items[1:],
        ),
    )
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest), cap="0.01")
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"
    assert "budget_cap_exceeded" in layer.suppression_reasons
    assert "manifest_live_join_mismatch" in layer.suppression_reasons


class _PayloadParser(HTMLParser):
    payload = ""
    capture = False

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        self.capture = tag == "script" and dict(attrs).get("id") == "antiek-bench-verdict"

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if tag == "script":
            self.capture = False

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if self.capture:
            self.payload += data


def test_json_and_html_are_redacted_and_no_evidence_is_not_measured(tmp_path: Path) -> None:
    manifest = _manifest()
    verdict = _build(tmp_path, manifest=manifest)
    rendered = project_weekly_verdict_html(verdict)
    parser = _PayloadParser()
    parser.feed(rendered)
    payload = json.loads(parser.payload)
    serialized = json.dumps(payload).lower()
    assert "private distill" not in rendered
    assert "rationale" not in serialized and "response" not in serialized and "secret" not in serialized
    assert "judge-1" not in serialized
    assert "candidate_hashes" not in serialized
    assert "evidence_id" not in serialized
    assert manifest.items[0].candidates[0].candidate_hash not in serialized
    assert verdict.judged_manifest_digest == manifest.mapping_digest
    assert "not measured" in rendered.lower()
    assert payload["auto_promotion"] is False
    assert payload["operator_acknowledgment_required"] is True


def test_ast_adds_no_dispatch_install_select_or_router_authority() -> None:
    tree = ast.parse(inspect.getsource(weekly_module))
    forbidden = ("dispatch", "install", "select", "router")
    callables = {
        node.name.casefold()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not {name for name in callables if any(word in name for word in forbidden)}
