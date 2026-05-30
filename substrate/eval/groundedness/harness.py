"""Offline groundedness harness (Foundation v2 SPR-02, M3).

Runs the deterministic groundedness scorer over (a) a hand-labeled set
of claims and (b) real on-disk Phase-6 traces, then reports the score
DISTRIBUTION and a SEPARATION statistic — does the score separate
faithful claims from hallucinated ones? This is the validate step that
earns the right to gate later (validate-before-gate). It is OFFLINE: it
reads on-disk JSONL/Parquet, opens no service, makes no network call.

Honesty (Rigor card 1): the harness reports the number it gets, weak or
strong — it never rounds up or drops inconvenient labeled cases.

Non-vacuity (Rigor card 3): the labeled set MUST contain at least one
true hallucination, or the harness ERRORS. A separation statistic over
faithful-only claims is meaningless.

Labeled-set format — one JSON object per line:

    {"id": "...", "label": "faithful"|"hallucinated",
     "claim": "...", "cited_chunk_ids": ["c1", ...],
     "chunk_texts": {"c1": "...", ...},   # inline → truly offline
     "note": "why this is labeled so (optional)"}

Trace mode — ``--traces <events-dir>``: reads SYNTHESIZE_DELIVERED
payloads from the event store and scores each synthesis's claims against
the chunks they cite (chunk text resolved from the DB at ``--db`` if
given, else from any inline ``chunk_texts`` already on the trace).

Usage:
    python -m substrate.eval.groundedness.harness \\
        --labeled tests/fixtures/groundedness_labeled.jsonl
    python -m substrate.eval.groundedness.harness \\
        --traces ~/.antiek/research_events --labeled <labels.jsonl>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from substrate.eval.groundedness.provenance import (
    duckdb_chunk_text_resolver,
    mapping_chunk_text_resolver,
)
from substrate.eval.groundedness.scorer import (
    DEFAULT_SUPPORTED_THRESHOLD,
    lexical_entailment_score,
)

FAITHFUL = "faithful"
HALLUCINATED = "hallucinated"
_VALID_LABELS = frozenset({FAITHFUL, HALLUCINATED})


@dataclass(frozen=True)
class LabeledCase:
    case_id: str
    label: str
    claim: str
    cited_chunk_ids: list[str]
    chunk_texts: dict[str, str]
    note: str = ""


@dataclass(frozen=True)
class SeparationReport:
    """The validate-step verdict. Every field is mechanically checkable
    against the promote-to-gate criterion (M5)."""

    n_faithful: int
    n_hallucinated: int
    faithful_mean: float
    hallucinated_mean: float
    mean_gap: float          # faithful_mean - hallucinated_mean
    auc: float               # rank-AUC: P(faithful score > hallucinated score)
    threshold_accuracy: float  # accuracy of supported>=threshold vs label
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_faithful": self.n_faithful,
            "n_hallucinated": self.n_hallucinated,
            "faithful_mean": round(self.faithful_mean, 4),
            "hallucinated_mean": round(self.hallucinated_mean, 4),
            "mean_gap": round(self.mean_gap, 4),
            "auc": round(self.auc, 4),
            "threshold_accuracy": round(self.threshold_accuracy, 4),
            "threshold": self.threshold,
        }


class LabeledSetError(ValueError):
    """Raised when the labeled set is missing or has no negatives — a
    separation statistic computed only over faithful claims is vacuous
    (Rigor card 3)."""


def load_labeled(path: str) -> list[LabeledCase]:
    cases: list[LabeledCase] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            obj = json.loads(line)
            label = obj.get("label")
            if label not in _VALID_LABELS:
                raise LabeledSetError(
                    f"{path}:{lineno}: label must be one of {sorted(_VALID_LABELS)}, "
                    f"got {label!r}"
                )
            cases.append(LabeledCase(
                case_id=str(obj.get("id", f"case-{lineno}")),
                label=label,
                claim=str(obj.get("claim", "")),
                cited_chunk_ids=[str(c) for c in (obj.get("cited_chunk_ids") or [])],
                chunk_texts={str(k): str(v) for k, v in (obj.get("chunk_texts") or {}).items()},
                note=str(obj.get("note", "")),
            ))
    return cases


def _rank_auc(faithful_scores: list[float], hallucinated_scores: list[float]) -> float:
    """P(a random faithful score > a random hallucinated score), ties=0.5.
    A standard rank-AUC. 1.0 = perfect separation, 0.5 = no separation."""
    if not faithful_scores or not hallucinated_scores:
        return 0.0
    wins = 0.0
    for fp in faithful_scores:
        for hp in hallucinated_scores:
            if fp > hp:
                wins += 1.0
            elif fp == hp:
                wins += 0.5
    return wins / (len(faithful_scores) * len(hallucinated_scores))


def score_labeled_set(
    cases: list[LabeledCase],
    *,
    threshold: float = DEFAULT_SUPPORTED_THRESHOLD,
) -> tuple[SeparationReport, list[tuple[LabeledCase, float, bool]]]:
    """Score every labeled case and compute the separation statistic.

    Errors if the set has no hallucinations (non-vacuity)."""
    if not cases:
        raise LabeledSetError("labeled set is empty")
    n_hallu = sum(1 for c in cases if c.label == HALLUCINATED)
    n_faith = sum(1 for c in cases if c.label == FAITHFUL)
    if n_hallu == 0:
        raise LabeledSetError(
            "labeled set has no hallucinations — a separation statistic over "
            "faithful-only claims is vacuous (Rigor card 3). Add at least one "
            "true hallucination the scorer must catch."
        )
    if n_faith == 0:
        raise LabeledSetError("labeled set has no faithful cases to separate from")

    rows: list[tuple[LabeledCase, float, bool]] = []
    faithful_scores: list[float] = []
    hallucinated_scores: list[float] = []
    correct = 0
    for case in cases:
        resolver = mapping_chunk_text_resolver(case.chunk_texts)
        chunk_texts = [t for cid in case.cited_chunk_ids if (t := resolver(cid))]
        score, _rationale = lexical_entailment_score(case.claim, chunk_texts)
        supported = score >= threshold
        rows.append((case, score, supported))
        if case.label == FAITHFUL:
            faithful_scores.append(score)
        else:
            hallucinated_scores.append(score)
        predicted_faithful = supported
        actual_faithful = case.label == FAITHFUL
        if predicted_faithful == actual_faithful:
            correct += 1

    faithful_mean = sum(faithful_scores) / len(faithful_scores)
    hallucinated_mean = sum(hallucinated_scores) / len(hallucinated_scores)
    report = SeparationReport(
        n_faithful=n_faith,
        n_hallucinated=n_hallu,
        faithful_mean=faithful_mean,
        hallucinated_mean=hallucinated_mean,
        mean_gap=faithful_mean - hallucinated_mean,
        auc=_rank_auc(faithful_scores, hallucinated_scores),
        threshold_accuracy=correct / len(cases),
        threshold=threshold,
    )
    return report, rows


# ---------------------------------------------------------------------------
# Trace mode — score real on-disk Phase-6 syntheses
# ---------------------------------------------------------------------------


def _iter_synthesis_payloads(events_dir: str) -> Iterable[tuple[str, dict]]:
    """Yield (investigation_id, synthesize.delivered payload dict) from the
    on-disk event store. Read-only over JSONL/Parquet via the event_log
    trajectory reader."""
    from substrate.event_log.events import trajectory

    if not os.path.isdir(events_dir):
        return
    for fn in sorted(os.listdir(events_dir)):
        if fn.endswith(".parquet"):
            iid = fn[: -len(".parquet")]
        elif fn.endswith(".jsonl"):
            iid = fn[: -len(".jsonl")]
        else:
            continue
        for row in trajectory(iid, events_dir=events_dir):
            if row.get("action_type") == "synthesize.delivered":
                payload = row.get("payload")
                if isinstance(payload, dict):
                    yield iid, payload


def score_traces(
    events_dir: str,
    *,
    db_path: str | None = None,
    threshold: float = DEFAULT_SUPPORTED_THRESHOLD,
) -> list[dict[str, Any]]:
    """Score every Phase-6 synthesis on disk. Returns one row per
    synthesis with its groundedness score + claim coverage. Chunk text is
    resolved from the DB at ``db_path`` if given; otherwise only inline
    ``chunk_texts`` already on the payload are used (so the harness still
    runs offline with no DB)."""
    from substrate.eval.groundedness.scorer import score_synthesis_groundedness

    rows: list[dict[str, Any]] = []
    # Gather all cited chunk ids first so the DB resolver loads once.
    all_payloads = list(_iter_synthesis_payloads(events_dir))
    all_chunk_ids: set[str] = set()
    for _iid, payload in all_payloads:
        for comp in payload.get("thesis_components") or []:
            for cid in comp.get("supporting_chunk_ids") or []:
                all_chunk_ids.add(str(cid))

    db_resolver = None
    if db_path:
        try:
            db_resolver = duckdb_chunk_text_resolver(
                db_path, chunk_ids=sorted(all_chunk_ids)
            )
        except Exception as exc:  # pragma: no cover — DB-absent path
            print(
                f"warning: could not open DB at {db_path}: {exc}; "
                "falling back to inline chunk_texts only",
                file=sys.stderr,
            )

    for iid, payload in all_payloads:
        # inline chunk_texts on the payload (some fixtures carry them)
        inline = payload.get("chunk_texts") or {}

        def _resolve(chunk_id: str, _inline=inline) -> str | None:
            if chunk_id in _inline:
                return _inline[chunk_id]
            return db_resolver(chunk_id) if db_resolver else None

        claim_chunks: list[tuple[str, list[str], list[str]]] = []
        for comp in payload.get("thesis_components") or []:
            claim = comp.get("claim")
            if not isinstance(claim, str):
                continue
            cids = [str(c) for c in (comp.get("supporting_chunk_ids") or [])]
            texts = [t for cid in cids if (t := _resolve(cid))]
            claim_chunks.append((claim, cids, texts))
        result = score_synthesis_groundedness(claim_chunks, supported_threshold=threshold)
        rows.append({
            "investigation_id": iid,
            "groundedness_score": round(result.score, 4),
            "scored_claims": result.scored_claims,
            "total_claims": result.total_claims,
        })
    return rows


def _format_distribution(scores: list[float]) -> str:
    if not scores:
        return "(no scores)"
    s = sorted(scores)
    n = len(s)

    def pct(p: float) -> float:
        return s[min(n - 1, int(p * n))]

    return (
        f"n={n} min={s[0]:.3f} p25={pct(0.25):.3f} "
        f"median={pct(0.5):.3f} p75={pct(0.75):.3f} max={s[-1]:.3f} "
        f"mean={sum(s)/n:.3f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m substrate.eval.groundedness.harness",
        description="Offline groundedness harness — score distribution + separation.",
    )
    parser.add_argument(
        "--labeled",
        help="Path to the hand-labeled JSONL set (faithful + >=1 hallucination).",
    )
    parser.add_argument(
        "--traces",
        help="Path to the on-disk event store (Phase-6 traces) to score.",
    )
    parser.add_argument(
        "--db",
        help="DuckDB path for chunk-text resolution in trace mode (optional).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SUPPORTED_THRESHOLD,
        help="Supported-threshold for the binary verdict.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human report.",
    )
    args = parser.parse_args(argv)

    if not args.labeled and not args.traces:
        parser.error("provide --labeled and/or --traces")

    out: dict[str, Any] = {}

    if args.labeled:
        cases = load_labeled(args.labeled)
        report, rows = score_labeled_set(cases, threshold=args.threshold)
        out["labeled"] = report.as_dict()
        out["labeled"]["faithful_distribution"] = _format_distribution(
            [s for c, s, _ in rows if c.label == FAITHFUL]
        )
        out["labeled"]["hallucinated_distribution"] = _format_distribution(
            [s for c, s, _ in rows if c.label == HALLUCINATED]
        )
        if not args.json:
            print("== Labeled-set separation ==")
            print(f"  faithful:     n={report.n_faithful} mean={report.faithful_mean:.3f}")
            print(f"  hallucinated: n={report.n_hallucinated} mean={report.hallucinated_mean:.3f}")
            print(f"  mean_gap:     {report.mean_gap:.3f}")
            print(f"  rank-AUC:     {report.auc:.3f}")
            print(f"  threshold acc: {report.threshold_accuracy:.3f} (@ {report.threshold})")
            print("  per-case:")
            for case, score, supported in rows:
                flag = "OK " if (supported == (case.label == FAITHFUL)) else "MISS"
                print(f"    [{flag}] {case.label:12s} {score:.3f}  {case.case_id}")

    if args.traces:
        trace_rows = score_traces(
            args.traces, db_path=args.db, threshold=args.threshold,
        )
        out["traces"] = {
            "n_syntheses": len(trace_rows),
            "distribution": _format_distribution(
                [r["groundedness_score"] for r in trace_rows]
            ),
            "rows": trace_rows,
        }
        if not args.json:
            print("== Trace distribution ==")
            print(f"  syntheses scored: {len(trace_rows)}")
            print(f"  groundedness:     {out['traces']['distribution']}")

    if args.json:
        print(json.dumps(out, indent=2))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
