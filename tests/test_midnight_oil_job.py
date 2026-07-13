from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import replace

import pytest

from substrate.midnight_oil.contracts import (
    REFUSED_GRAPH_ADMISSION_REASONS,
    RETRYABLE_GRAPH_ADMISSION_REASONS,
    GraphAdmissionReason,
)
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    MidnightOilStepEvidence,
    _job_from_row,
    _job_to_row,
    build_step_claim_evidence,
    create_job,
    source_receipt_id,
)
from substrate.midnight_oil.worker import (
    WorkerClaimSupport,
    WorkerStepResult,
    _step_evidence,
)


def _receipt(**changes: str) -> dict[str, str]:
    receipt = {
        "source_id": "chunk|1",
        "document_id": "document|1",
        "source_url": "antiek://document/document|1#chunk=chunk|1",
        "content_hash": hashlib.sha256(b"exact local text").hexdigest(),
        "hash_scope": "retrieval_excerpt",
        "title": "Display title",
    }
    receipt.update(changes)
    return receipt


def test_claim_census_preserves_supported_unverified_and_exploratory_states() -> None:
    receipt = _receipt()
    receipt_id = source_receipt_id(receipt)
    claims = build_step_claim_evidence(
        job_id="job|one",
        step_key="step|one",
        output_text="Supported paragraph.\r\n\r\nUnverified paragraph.",
        insights=("Supported insight.", "Unverified insight."),
        questions=("What remains open?",),
        source_receipts=(receipt,),
        supported_claims=(
            ("output_paragraph", 0, (receipt_id,)),
            ("insight", 0, (receipt_id,)),
        ),
    )

    assert [claim.status for claim in claims] == [
        "supported",
        "unverified",
        "supported",
        "unverified",
        "exploratory",
    ]
    assert len({claim.claim_id for claim in claims}) == len(claims)
    assert claims[0].normalized_text == "Supported paragraph."
    assert claims[-1].source_receipt_ids == ()


def test_duplicate_unknown_and_exploratory_support_mappings_reject() -> None:
    receipt = _receipt()
    receipt_id = source_receipt_id(receipt)
    common = {
        "job_id": "job",
        "step_key": "step",
        "output_text": "paragraph",
        "insights": (),
        "questions": ("question",),
        "source_receipts": (receipt,),
    }
    with pytest.raises(ValueError, match="duplicate"):
        build_step_claim_evidence(
            **common,
            supported_claims=(
                ("output_paragraph", 0, (receipt_id,)),
                ("output_paragraph", 0, (receipt_id,)),
            ),
        )
    with pytest.raises(ValueError, match="unknown source"):
        build_step_claim_evidence(
            **common,
            supported_claims=(("output_paragraph", 0, ("0" * 64,)),),
        )
    with pytest.raises(ValueError, match="exploratory"):
        build_step_claim_evidence(
            **common,
            supported_claims=(("exploratory_question", 0, (receipt_id,)),),
        )
    with pytest.raises(ValueError, match="duplicate source"):
        build_step_claim_evidence(
            **{**common, "source_receipts": (receipt, dict(receipt))},
            supported_claims=(),
        )


def test_receipt_identity_ignores_key_order_and_display_title() -> None:
    receipt = _receipt()
    reordered = dict(reversed(tuple(receipt.items())))
    renamed = {**receipt, "title": "Different display title"}

    assert source_receipt_id(receipt) == source_receipt_id(reordered)
    assert source_receipt_id(receipt) == source_receipt_id(renamed)
    with pytest.raises(ValueError, match="conflicts"):
        source_receipt_id({**receipt, "receipt_id": "0" * 64})


def test_worker_normalization_redacts_before_claim_identity_and_leaves_unmapped_unverified() -> (
    None
):
    evidence = _step_evidence(
        WorkerStepResult(
            spent_usd=0.01,
            output_text="Result sk-secretvalue123456.",
            insights=("Insight api_key=secretvalue123456",),
            questions=("What remains?",),
        ),
        job_id="job",
        step_key="step",
    )

    assert "secretvalue" not in evidence.output_text
    assert "secretvalue" not in evidence.insights[0]
    assert evidence.claim_evidence_schema_version == 1
    assert [claim.status for claim in evidence.claim_evidence] == [
        "unverified",
        "unverified",
        "exploratory",
    ]


@pytest.mark.parametrize(
    "result",
    [
        WorkerStepResult(spent_usd=0.0, output_text="x" * 200_001),
        WorkerStepResult(spent_usd=0.0, insights=("x",) * 101),
        WorkerStepResult(spent_usd=0.0, questions=("x",) * 101),
        WorkerStepResult(spent_usd=0.0, source_receipts=(_receipt(),) * 101),
        WorkerStepResult(spent_usd=0.0, spawn_id="x" * 513),
        WorkerStepResult(spent_usd=0.0, route_receipt={"event_id": "x" * 2_049}),
        WorkerStepResult(spent_usd=0.0, route_receipt={"unexpected": "metadata"}),
        WorkerStepResult(spent_usd=0.0, route_receipt={"provider": "test"}),
        WorkerStepResult(
            spent_usd=0.0, route_receipt={"provider": "", "model": "test"}
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={"provider": "test", "model": "test", "tier": ""},
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={"provider": "test", "model": "test", "event_id": ""},
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "fallback_chain_index": -1,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "fallback_chain_index": True,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "fallback_chain_index": 2_049,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "actual_cost_usd": math.inf,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "actual_cost_usd": -0.01,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "actual_cost_usd": True,
            },
        ),
        WorkerStepResult(
            spent_usd=0.0,
            route_receipt={
                "provider": "test",
                "model": "test",
                "actual_cost_usd": 10**1_000,
            },
        ),
    ],
)
def test_worker_rejects_oversized_evidence_instead_of_checkpointing_a_partial_census(
    result: WorkerStepResult,
) -> None:
    with pytest.raises(ValueError, match="durable v1 envelope"):
        _step_evidence(result, job_id="job", step_key="step")


def test_versioned_claim_evidence_round_trips_and_legacy_stays_unversioned() -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="job")
    receipt = _receipt()
    receipt_id = source_receipt_id(receipt)
    evidence = _step_evidence(
        WorkerStepResult(
            spent_usd=0.01,
            output_text="paragraph",
            source_receipts=(receipt,),
            claim_support=(WorkerClaimSupport("output_paragraph", 0, (receipt_id,)),),
        ),
        job_id=job.job_id,
        step_key="step",
    )
    restored = _job_from_row(_job_to_row(replace(job, step_evidence=(evidence,))))

    assert restored.step_evidence == (evidence,)
    legacy = MidnightOilStepEvidence("legacy", None, "old prose", (), ())
    legacy_restored = _job_from_row(
        _job_to_row(replace(job, step_evidence=(legacy,)))
    ).step_evidence[0]
    assert legacy_restored.claim_evidence_schema_version is None
    assert legacy_restored.claim_evidence == ()


def test_durable_duplicate_claim_id_rejects_instead_of_inventing_coverage() -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="job")
    evidence = _step_evidence(
        WorkerStepResult(spent_usd=0.0, output_text="one\n\ntwo"),
        job_id=job.job_id,
        step_key="step",
    )
    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    claims = row["step_evidence"][0]["claim_evidence"]
    claims[1]["claim_id"] = claims[0]["claim_id"]

    with pytest.raises(ValueError, match="duplicate|identity"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence"] = None
    with pytest.raises(ValueError, match="malformed"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence"][0].pop("status")
    with pytest.raises(ValueError, match="malformed"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["source_receipts"] = [{**_receipt(), "receipt_id": "0" * 64}]
    with pytest.raises(ValueError, match="conflicts"):
        _job_from_row(row)


def test_versioned_hostile_or_oversized_evidence_fails_closed() -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="job")
    receipt = _receipt()
    evidence = _step_evidence(
        WorkerStepResult(spent_usd=0.0, output_text="claim", source_receipts=(receipt,)),
        job_id=job.job_id,
        step_key="step",
    )

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence_schema_version"] = 2
    with pytest.raises(ValueError, match="version"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence"] *= 2_049
    with pytest.raises(ValueError, match="malformed"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence"][0]["normalized_text"] = "x" * 200_001
    with pytest.raises(ValueError, match="malformed"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["claim_evidence"][0]["source_receipt_ids"] = ["0" * 64] * 101
    with pytest.raises(ValueError, match="malformed"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["source_receipts"] = [{"document_id": "partial"}]
    with pytest.raises(ValueError, match="source receipt evidence"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["source_receipts"] *= 101
    with pytest.raises(ValueError, match="source receipt evidence"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["source_receipts"][0]["unexpected"] = "metadata"
    with pytest.raises(ValueError, match="source receipt evidence"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["route_receipt"] = {"unexpected": "metadata"}
    with pytest.raises(ValueError, match="route receipt"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["route_receipt"] = {"provider": "test"}
    with pytest.raises(ValueError, match="route receipt"):
        _job_from_row(row)

    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    row["step_evidence"][0]["spawn_id"] = "x" * 513
    with pytest.raises(ValueError, match="versioned step evidence"):
        _job_from_row(row)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.pop("step_key"),
        lambda item: item.__setitem__("output_text", 7),
        lambda item: item.__setitem__("insights", ["x"] * 101),
        lambda item: item.__setitem__("unexpected", "field"),
    ],
)
def test_versioned_step_envelope_rejects_drop_coercion_and_partial_recovery(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="job")
    evidence = _step_evidence(
        WorkerStepResult(spent_usd=0.0, output_text="claim"),
        job_id=job.job_id,
        step_key="step",
    )
    row = _job_to_row(replace(job, step_evidence=(evidence,)))
    mutate(row["step_evidence"][0])

    with pytest.raises(ValueError, match="versioned step evidence"):
        _job_from_row(row)


def test_durable_step_census_rejects_non_object_entries() -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="job")
    row = _job_to_row(job)
    row["step_evidence"] = [None]

    with pytest.raises(ValueError, match="step evidence"):
        _job_from_row(row)


@pytest.mark.parametrize("reason", sorted(REFUSED_GRAPH_ADMISSION_REASONS))
def test_permanent_graph_refusal_round_trips_without_an_effect_receipt(
    reason: GraphAdmissionReason,
) -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id=f"refused-{reason}")
    refused = replace(
        job,
        graph_projection_state="refused",
        graph_projection_reason=reason,
    )

    restored = _job_from_row(_job_to_row(refused))

    assert restored.graph_projection_state == "refused"
    assert restored.graph_projection_reason == reason
    assert restored.graph_effect_receipt is None


@pytest.mark.parametrize("reason", sorted(RETRYABLE_GRAPH_ADMISSION_REASONS))
def test_retryable_graph_reason_remains_pending_after_restart(
    reason: GraphAdmissionReason,
) -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id=f"pending-{reason}")
    pending = replace(job, graph_projection_reason=reason)

    restored = _job_from_row(_job_to_row(pending))

    assert restored.graph_projection_state == "pending"
    assert restored.graph_projection_reason == reason
    assert restored.graph_effect_receipt is None


def test_graph_projection_disposition_rejects_state_reason_drift() -> None:
    store = InMemoryJobStore()
    job = create_job(["goal"], 5, store=store, job_id="disposition-drift")

    with pytest.raises(ValueError, match="pending graph projection"):
        _job_to_row(replace(job, graph_projection_reason="legacy_unverified"))
    with pytest.raises(ValueError, match="permanent reason"):
        _job_to_row(
            replace(
                job,
                graph_projection_state="refused",
                graph_projection_reason="graph_lock_unavailable",
            )
        )

    row = _job_to_row(job)
    row["graph_projection_reason"] = "invented_reason"
    with pytest.raises(ValueError, match="reason is unsupported"):
        _job_from_row(row)
