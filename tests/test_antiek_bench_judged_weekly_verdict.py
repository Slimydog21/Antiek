from __future__ import annotations

import ast
import hashlib
import inspect
import json
from dataclasses import replace
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_antiek_bench_weekly_verdict import journals, suite

from substrate.antiek_bench.judged import EvidenceRecord, VerdictPolicy, rubric_for
from substrate.antiek_bench.live import (
    JudgedCandidateJoin,
    JudgedItemJoin,
    JudgedJoinManifest,
    build_weekly_verdict,
    project_weekly_verdict_html,
)
from substrate.antiek_bench.live import weekly_verdict as weekly_module


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _manifest() -> JudgedJoinManifest:
    return JudgedJoinManifest(
        week_id="2026-W28",
        suite_version="live-suite-v1",
        items=tuple(
            JudgedItemJoin(
                task_class=item.task_class,
                live_item_id=item.item_id,
                live_prompt_hash=_hash(item.prompt),
                item_id_hash=_hash("salt:item:" + item.item_id),
                candidates=(
                    JudgedCandidateJoin(
                        "model-a",
                        hashlib.sha256(f"response:model-a:{item.item_id}".encode()).hexdigest(),
                        _hash("salt:a:" + item.item_id),
                    ),
                    JudgedCandidateJoin(
                        "model-b",
                        hashlib.sha256(f"response:model-b:{item.item_id}".encode()).hexdigest(),
                        _hash("salt:b:" + item.item_id),
                    ),
                ),
                rubric_version=rubric_for(item.task_class).version,
                allowed_judges=("judge-1",),
            )
            for item in suite().items
        ),
    )


def _evidence(manifest: JudgedJoinManifest) -> tuple[EvidenceRecord, ...]:
    rows: list[EvidenceRecord] = []
    for item in manifest.items:
        axes = rubric_for(item.task_class).axes
        pair = tuple(candidate.candidate_hash for candidate in item.candidates)
        for candidate_hashes, score in ((pair, 5), (tuple(reversed(pair)), 1)):
            rows.append(
                EvidenceRecord(
                    week_id=manifest.week_id,
                    suite_version=manifest.suite_version,
                    item_id_hash=item.item_id_hash,
                    task_class=item.task_class,  # type: ignore[arg-type]
                    rubric_version=item.rubric_version,
                    judge_model="judge-1",
                    candidate_hashes=candidate_hashes,  # type: ignore[arg-type]
                    blinded_order=("A", "B"),
                    status="ok",
                    claimed_at_ms=1,
                    scores=tuple((axis, score) for axis in axes),
                    evidence_refs=tuple((axis, ("A:fact",)) for axis in axes),
                )
            )
    return tuple(rows)


def _build(tmp_path: Path, *, manifest=None, evidence=(), cap="1"):  # type: ignore[no-untyped-def]
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
    forged = replace(
        manifest,
        items=(replace(first, candidates=(forged_candidate, first.candidates[1])), *manifest.items[1:]),
    )
    verdict = _build(tmp_path, manifest=forged, evidence=_evidence(manifest))
    layer = next(task.judged for task in verdict.task_verdicts if task.task_class == "distill")
    assert layer is not None and layer.status == "NOT MEASURED"
    assert "manifest_live_join_mismatch" in layer.suppression_reasons


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
    forged = replace(
        manifest,
        items=(
            replace(
                first,
                candidates=(
                    JudgedCandidateJoin("forged-model", "forged-response", _hash("forged")),
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
