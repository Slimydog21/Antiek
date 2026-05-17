"""Decomposer few-shot example mining (Sprint 5 day 4-5 migration).

Direct port of Researchmaxx ``seed_decomposer_examples.py``. Scans
archived syntheses + their outcomes for trajectories that meet the
admission criteria, and produces ``DecomposerExampleProposal``
records.

There is NO automatic admission to ``examples.jsonl``. A human
reviewer must inspect each proposal and move accepted entries by
hand — admitting a misleading few-shot is more costly than not
admitting any at all (same rationale as upstream).

Admission criteria (all must hold):

  1. syntheses.status == "passed"
  2. ≥1 outcome row with outcome ∈ {confirmed, partially_confirmed}
  3. No flagged paraphrase entries in
     ``model_versions.paraphrase_history``
  4. The agent_trace contains a decomposer record with
     ``parsed.decomposition``

The DB query (joining syntheses + outcomes) is DEFERRED — it depends
on ``substrate/init_db.py`` extending to the syntheses + outcomes
tables. The pure mining function
``propose_examples_from_rows(rows)`` ships now, taking pre-loaded row
tuples; the operator CLI + DB loader wire in alongside the table
migration.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, List, Optional

try:
    from ...constants import ANTIEK_PARAM_VERSION
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import ANTIEK_PARAM_VERSION  # type: ignore[no-redef]


# Confirmed-grade thesis outcomes count as positive trajectory signal.
# Mirrors the upstream's outcome-counting set.
_POSITIVE_OUTCOME_STATUSES: frozenset[str] = frozenset({
    "confirmed", "partially_confirmed",
})


@dataclass(frozen=True)
class CandidateRow:
    """One (synthesis, outcome) join row from the loader. Outcomes are
    LEFT-JOINed so the outcome columns may be None for syntheses with
    no observations yet — those rows fail criterion 2 silently."""

    synthesis_id: str
    investigation_id: str
    synthesis_timestamp: str
    agent_trace_json: Any
    model_versions_json: Any
    thesis_outcomes_json: Any  # may be None


@dataclass
class DecomposerExampleProposal:
    """One mined proposal. ``admitted_at`` is always None at proposal
    time — the human reviewer sets it when promoting to
    ``examples.jsonl``."""

    example_id: str
    source_synthesis_id: str
    source_investigation_id: str
    param_version: str
    admitted_at: Optional[str]
    admission_reason: str
    synthesis_timestamp: str
    input_raw: dict
    output: dict
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_load_json(value: Any) -> Any:
    """Tolerate either pre-parsed Python objects or raw JSON strings.
    Returns None on parse failure (caller treats as ineligible)."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_decomposer_io(agent_trace_json: Any) -> Optional[dict]:
    """Pull the Decomposer's user prompt + parsed output from a trace
    blob. Returns the first matching record, or None when the trace
    contains no decomposer step (criterion 4 fails)."""
    trace = _safe_load_json(agent_trace_json)
    if not trace:
        return None
    for rec in trace:
        if not isinstance(rec, dict):
            continue
        if rec.get("role") != "decomposer":
            continue
        parsed = rec.get("parsed") or {}
        if isinstance(parsed, dict) and parsed.get("decomposition"):
            return rec
    return None


def paraphrase_clean(model_versions_json: Any) -> bool:
    """True iff no paraphrase flagging occurred in this trajectory
    (criterion 3). A None or malformed blob is treated as clean only
    when None — malformed JSON fails closed because we cannot prove
    cleanliness."""
    if model_versions_json is None:
        return True
    mv = _safe_load_json(model_versions_json)
    if mv is None:
        return False
    hist = mv.get("paraphrase_history") or []
    return all(not entry.get("flagged") for entry in hist if isinstance(entry, dict))


def count_confirmed(thesis_outcomes_json: Any) -> int:
    """Number of thesis_outcomes entries with outcome ∈
    ``_POSITIVE_OUTCOME_STATUSES``. 0 on missing-or-malformed input."""
    if not thesis_outcomes_json:
        return 0
    data = _safe_load_json(thesis_outcomes_json)
    if not data:
        return 0
    return sum(
        1 for o in data
        if isinstance(o, dict) and o.get("outcome") in _POSITIVE_OUTCOME_STATUSES
    )


def propose_examples_from_rows(
    rows: Iterable[CandidateRow],
    *,
    limit: int = 50,
) -> List[DecomposerExampleProposal]:
    """Pure mining function. Takes pre-loaded LEFT-JOIN rows, returns
    proposals in synthesis_timestamp-descending order (newest first).

    Multiple rows for the same synthesis_id (one synthesis, several
    outcome observations) are aggregated: confirmed counts are summed
    across observations. Trace + model_versions blobs are taken from
    the FIRST row seen for each synthesis (they're synthesis-level
    columns, identical across observations).
    """
    # Group rows by synthesis_id, summing confirmed counts.
    by_synth: dict[str, dict] = {}
    for r in rows:
        rec = by_synth.setdefault(r.synthesis_id, {
            "iid": r.investigation_id,
            "ts": r.synthesis_timestamp,
            "trace_json": r.agent_trace_json,
            "mv_json": r.model_versions_json,
            "confirmed": 0,
        })
        rec["confirmed"] += count_confirmed(r.thesis_outcomes_json)

    proposals: List[DecomposerExampleProposal] = []
    for sid, rec in sorted(by_synth.items(),
                           key=lambda kv: kv[1]["ts"] or "",
                           reverse=True):
        if rec["confirmed"] < 1:
            continue  # criterion 2
        if not paraphrase_clean(rec["mv_json"]):
            continue  # criterion 3
        dec = extract_decomposer_io(rec["trace_json"])
        if not dec:
            continue  # criterion 4

        proposals.append(DecomposerExampleProposal(
            example_id=f"ex_{rec['iid']}_{sid[:8]}",
            source_synthesis_id=sid,
            source_investigation_id=rec["iid"],
            param_version=ANTIEK_PARAM_VERSION,
            admitted_at=None,
            admission_reason=(
                f"status=passed; confirmed_outcomes={rec['confirmed']}; "
                f"no paraphrase flags"
            ),
            synthesis_timestamp=str(rec["ts"]),
            input_raw={"user_prompt": dec.get("user_prompt")},
            output=dec.get("parsed") or {},
        ))
        if len(proposals) >= limit:
            break
    return proposals
