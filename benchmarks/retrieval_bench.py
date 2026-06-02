"""SPR-05 M2/M3 — retrieval-substrate benchmark harness.

Measures, for each candidate ``RetrievalSubstrate`` on the SAME seeded graph
and SAME labeled query fixture:

  - recall@k (arithmetic, |top-k ∩ relevant| / |relevant|) — POOLED and
    PER-DOMAIN (OPERATOR_INPUTS §1 clause 1: per-domain so the quantum
    monoculture cannot carry the verdict), and split LOAD-BEARING vs not
    (§1 clause 5 + the stub-embedder caveat),
  - rank-based negative controls (§1 clause 3: search() has no similarity
    threshold, so "expect nothing" is scored as "no control chunk outranks the
    lowest-ranked true positive of its paired positive query"),
  - the §9.0 gate check (§1 clause 4: a candidate returning a
    `restricted_pending_opt_in` chunk under attribution_eligible FAILS),
  - p50/p95 query latency over repeated runs,
  - one-time index-build wall-time (recorded SEPARATELY so a fast query that
    hides an expensive index is not free).

Compose, do not invent: the seed/timing scaffolding follows
``benchmarks/context_pack_timing.py`` (``_HashEmbedding`` + ``connect_write``
seed + percentile timing); the recall arithmetic reuses ``_safe_div`` from
``substrate/research_bridge/eval/scoring.py``; the YAML loader follows the
pattern in ``substrate/research_bridge/eval/labels.py``.

Usage:

    python -m benchmarks.retrieval_bench --substrate vss
    python -m benchmarks.retrieval_bench --substrate vss --substrate turbopuffer --substrate ducklake

Emits a JSON comparison artifact at
``benchmarks/out/retrieval_spike_<YYYY-MM-DD>.json``.

HONESTY (load-bearing): the only embedder available in CI is the dim-16
``_HashEmbedding`` stub. It carries NO semantic structure, so paraphrase /
conceptual recall under it is NON-LOAD-BEARING — it measures index mechanics +
speed, not ranking quality. The harness reports load-bearing and non-load-
bearing recall separately and never presents stub recall as if it discriminated
semantic quality. Run under all-MiniLM-L6-v2 (sentence-transformers) to lift
the non-load-bearing flags.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- compose imports -------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.graph.retrieval_substrate import make_substrate  # noqa: E402
from substrate.research_bridge.eval.scoring import _safe_div  # noqa: E402

MIN_QUERIES = 20  # NOTE: §1 dropped Q15 ⇒ 19 operator queries; see _load_fixture.
DEFAULT_TOP_K = 5
LATENCY_REPEATS = 30


# ---------------------------------------------------------------------------
# Deterministic embedder (the only one available in CI) — composed from
# context_pack_timing._HashEmbedding.
# ---------------------------------------------------------------------------


class HashEmbedding:
    """dim-16 deterministic hash embedder. Same chunk → same vector. Carries
    NO semantic structure — see the module honesty note."""

    dimension = 16
    name = "hash-stub-dim16"
    semantic = False

    def encode(self, text: str) -> list[float]:
        import hashlib

        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


def _real_embedder_or_none():
    """Return the real all-MiniLM-L6-v2 embedder if sentence-transformers is
    installed, else None. The decision record records which embedder ran."""
    try:
        from substrate.graph.search import SentenceTransformerEmbedding

        emb = SentenceTransformerEmbedding("all-MiniLM-L6-v2")
        emb.name = "all-MiniLM-L6-v2"
        emb.semantic = True
        return emb
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fixture loading + validation (the size guard)
# ---------------------------------------------------------------------------


class FixtureTooSmall(RuntimeError):
    """Raised when the labeled query set has fewer than MIN_QUERIES queries."""


@dataclass(frozen=True)
class LabeledQuery:
    id: str
    type: str
    query: str
    target: str            # "chunks" | "nodes"
    domain: str
    relevant: tuple[str, ...]
    label_provenance: str  # fixture | author-asserted | structural
    load_bearing: bool
    top_k: int = DEFAULT_TOP_K
    source_tier_max: int | None = None
    policy_tag: str = "attribution_eligible"
    paired_positive: str | None = None
    must_not_return: tuple[str, ...] = ()


def _default_fixture_path() -> Path:
    return Path(_REPO) / "benchmarks" / "fixtures" / "retrieval_queries.yaml"


def _load_fixture(path: Path | str, *, min_queries: int = MIN_QUERIES) -> tuple[list[LabeledQuery], dict]:
    """Load + validate the YAML fixture. Refuses (raises FixtureTooSmall) if
    the fixture has fewer than ``min_queries`` queries — no silent run on a
    thin set (M2 acceptance).

    NOTE on the count: OPERATOR_INPUTS §1 dropped Q15 (the seeded-hallucination
    trap), leaving 19 operator queries (Q01-Q14, Q16-Q20). The fixture reaches
    the spec's ≥20 floor by adding ONE structural rank-based negative control
    (Q21) in a disjoint out-of-corpus domain — strengthening §1 clause 3, not
    diluting the operator set with author-asserted relevance. The guard still
    REFUSES a genuinely thin set (the size-guard test points it at a 5-query
    fixture and expects refusal)."""
    import yaml

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"fixture not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    meta = raw.get("meta", {}) or {}
    qs_raw = raw.get("queries", []) or []
    queries: list[LabeledQuery] = []
    for q in qs_raw:
        if not isinstance(q, dict) or not q.get("id"):
            continue
        queries.append(LabeledQuery(
            id=str(q["id"]),
            type=str(q.get("type", "")),
            query=str(q.get("query", "")),
            target=str(q.get("target", "chunks")),
            domain=str(q.get("domain", "default")),
            relevant=tuple(str(x) for x in (q.get("relevant") or ())),
            label_provenance=str(q.get("label_provenance", "author-asserted")),
            load_bearing=bool(q.get("load_bearing", True)),
            top_k=int(q.get("top_k", meta.get("default_top_k", DEFAULT_TOP_K))),
            source_tier_max=q.get("source_tier_max"),
            policy_tag=str(q.get("policy_tag", "attribution_eligible")),
            paired_positive=q.get("paired_positive"),
            must_not_return=tuple(str(x) for x in (q.get("must_not_return") or ())),
        ))
    if len(queries) < min_queries:
        raise FixtureTooSmall(
            f"fixture has {len(queries)} queries, need >={min_queries}"
        )
    return queries, meta


# ---------------------------------------------------------------------------
# Deterministic synthetic graph seed — matches the §1 labels.
# Composes context_pack_timing's connect_write + promote_insight pattern.
# ---------------------------------------------------------------------------

# (document_id, source_tier, content_class, chunk_id, text)
_SEED_CHUNKS = [
    # quantum — neutral atom
    ("doc-quera", 1, "public_domain", "c-quera-1",
     "QuEra neutral-atom array demonstrated single-qubit gate error rate near "
     "0.1 percent at the 100-qubit scale, a key milestone for scaling."),
    # radar
    ("doc-radar", 2, "public_domain", "c-radar-1",
     "The phased-array radar achieved 35 dB antenna gain with sidelobe "
     "suppression of 25 dB through amplitude tapering across the aperture."),
    # batteries — multi-hop
    ("doc-lfp", 2, "public_domain", "c-lfp-1",
     "LiFePO4 cells retained roughly 80 percent of rated capacity after 2000 "
     "charge-discharge cycles under the tested conditions."),
    ("doc-lfp", 2, "public_domain", "c-lfp-2",
     "Capacity retention for the lithium iron phosphate chemistry was measured "
     "at 25 C and 1C rate over the full cycling protocol."),
    # vaccines — paraphrase target
    ("doc-vax", 2, "public_domain", "c-vax-1",
     "The phase-three clinical trial reported vaccine efficacy of 94 percent "
     "against symptomatic disease in the late-stage cohort."),
    # superconducting decoherence cluster (conceptual / paraphrase)
    ("doc-decoh", 2, "public_domain", "c-decoh-1",
     "Quasiparticle tunneling is a dominant decoherence mechanism in cryogenic "
     "superconducting transmon qubits at millikelvin temperatures."),
    ("doc-decoh", 2, "public_domain", "c-decoh-2",
     "Two-level-system defects in the amorphous oxide couple to the qubit and "
     "destroy phase coherence in superconducting hardware."),
    ("doc-decoh", 2, "public_domain", "c-decoh-3",
     "Dielectric loss and thermal photon noise further limit coherence times of "
     "superconducting qubits held at cryogenic temperature."),
    # photonics — loss + fidelity scaling
    ("doc-photon", 2, "public_domain", "c-photon-loss-1",
     "Optical photon loss in waveguides sets the ceiling on loss-tolerant gate "
     "performance for photonic quantum computing architectures."),
    ("doc-photon", 2, "public_domain", "c-photon-fidelity-1",
     "Photonic two-qubit gate fidelity degrades as the qubit count grows "
     "because accumulated loss scales with circuit depth."),
    # QEC threshold
    ("doc-qec", 1, "public_domain", "c-qec-1",
     "The quantum error-correction threshold theorem implies fault tolerance is "
     "achievable once physical error rates fall below about 1 percent."),
    # bridges
    ("doc-bridge", 3, "public_domain", "c-bridge-1",
     "The cable-stayed bridge carries a load rating of 12 tonnes per axle on "
     "the main span per the design specification."),
    # §9.0 gate control — RESTRICTED content (Q20). Topically a quantum chunk so
    # a naive index would surface it; the gate must withhold it.
    ("doc-restricted", 2, "restricted_pending_opt_in", "c-restricted-1",
     "Restricted Big-Five book chunk discussing quantum computing milestones "
     "pending publisher opt-in."),
]

# Insight / question nodes for the node-retrieval queries (Q08/Q10/Q11). Their
# canonical_label is the relevant-set label in the fixture (ILIKE node path).
_SEED_INSIGHTS = [
    "Error suppression improves with neutral-atom array scaling",
    "Conditional yes if neutral-atom error rates hold while scaling",
]
_SEED_QUESTIONS = [
    "Can neutral-atom platforms cross 1000-qubit scale by 2027?",
]


def seed_graph(db_path: str, embedder: Any) -> dict:
    """Seed the deterministic synthetic graph. Returns baseline row counts so
    the §16 read-only test can assert they are unchanged after a query run."""
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import promote_insight, promote_question
    from substrate.graph.schema import init_database

    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    con = connect_write(db_path, purpose="retrieval_bench_seed")
    try:
        init_database(con)
        con.execute("BEGIN")
        seen_docs: set[str] = set()
        for doc_id, tier, cclass, chunk_id, text in _SEED_CHUNKS:
            if doc_id not in seen_docs:
                con.execute(
                    "INSERT INTO documents (document_id, title, source_tier, "
                    "document_type, content_class) VALUES (?, ?, ?, 'paper', ?)",
                    [doc_id, f"Title for {doc_id}", tier, cclass],
                )
                seen_docs.add(doc_id)
            emb = embedder.encode(text)
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, 0, ?, ?, ?)",
                [chunk_id, doc_id, text, emb, max(1, len(text) // 4)],
            )
        con.execute("COMMIT")
        # Nodes for the node-retrieval path.
        for text in _SEED_INSIGHTS:
            promote_insight(text=text, investigation_id="bench",
                            confidence="moderate", embedding_provider=embedder, con=con)
        for text in _SEED_QUESTIONS:
            promote_question(text=text, investigation_id="bench",
                             embedding_provider=embedder, con=con)
    finally:
        con.close()
    return row_counts(db_path)


def row_counts(db_path: str) -> dict:
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        return {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("chunks", "nodes", "edges")
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _retrieved_ids(result: dict, target: str) -> list[str]:
    """Ordered retrieved ids for a query, by target field."""
    if target == "nodes":
        # node_matches are ILIKE label hits; score by canonical label.
        return [m.get("label", "") for m in result.get("node_matches", [])]
    return [r.get("chunk_id", "") for r in result.get("results", [])]


def recall_at_k(retrieved: list[str], relevant: tuple[str, ...], k: int) -> float | None:
    """|top-k ∩ relevant| / |relevant|. None when there is no relevant set
    (negative / gate controls are scored separately, not by recall)."""
    if not relevant:
        return None
    topk = set(retrieved[:k])
    hit = sum(1 for r in relevant if r in topk)
    return _safe_div(hit, len(relevant))


@dataclass
class QueryResult:
    id: str
    domain: str
    load_bearing: bool
    label_provenance: str
    recall: float | None
    retrieved: list[str] = field(default_factory=list)
    note: str = ""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# ---------------------------------------------------------------------------
# Run one candidate
# ---------------------------------------------------------------------------


def run_candidate(
    kind: str,
    db_path: str,
    queries: list[LabeledQuery],
    embedder: Any,
    *,
    latency_repeats: int = LATENCY_REPEATS,
) -> dict:
    """Run one substrate candidate over the whole fixture. Returns a report
    dict. Credential-gated adapters (turbopuffer/ducklake) self-report
    ``status: skipped — no credentials`` and emit a skipped report rather than
    crash."""
    build_t0 = time.perf_counter()
    sub = make_substrate(kind, db_path, model=embedder)
    build_ms = (time.perf_counter() - build_t0) * 1000.0

    skipped_status = getattr(sub, "status", None)
    if skipped_status:
        try:
            sub.close()
        except Exception:
            pass
        return {
            "substrate": kind,
            "status": skipped_status,
            "build_ms": round(build_ms, 3),
        }

    vss_active = getattr(sub, "vss_active", None)

    per_query: list[QueryResult] = []
    latencies_ms: list[float] = []
    gate_leak: str | None = None
    neg_control_violations: list[str] = []

    # First pass: correctness (recall + gate + capture retrieved for rank ctrl).
    retrieved_by_id: dict[str, list[str]] = {}
    sim_by_id: dict[str, list[tuple[str, float]]] = {}
    for q in queries:
        res = sub.query(
            q.query, top_k=max(q.top_k, 10), source_tier_max=q.source_tier_max,
            document_ids=None, policy_tag=q.policy_tag,
        )
        retrieved = _retrieved_ids(res, q.target)
        retrieved_by_id[q.id] = retrieved
        # capture (chunk_id, similarity) for rank-based negative controls
        if q.target == "chunks":
            sim_by_id[q.id] = [
                (r.get("chunk_id", ""), float(r.get("similarity", 0.0)))
                for r in res.get("results", [])
            ]
        rec = recall_at_k(retrieved, q.relevant, q.top_k)
        note = ""
        # §9.0 gate control (Q20): a must_not_return id appearing under
        # attribution_eligible is a correctness/legal FAIL independent of recall.
        if q.must_not_return:
            leaked = [m for m in q.must_not_return if m in retrieved]
            if leaked:
                gate_leak = q.id
                note = f"GATE LEAK: {leaked} returned under {q.policy_tag}"
            else:
                note = f"gate held: {list(q.must_not_return)} withheld"
        per_query.append(QueryResult(
            id=q.id, domain=q.domain, load_bearing=q.load_bearing,
            label_provenance=q.label_provenance, recall=rec,
            retrieved=retrieved, note=note,
        ))

    # Rank-based negative controls (§1 clause 3): no negative-control chunk may
    # outrank the lowest-ranked TRUE positive of its paired positive query.
    qmap = {q.id: q for q in queries}
    for q in queries:
        if q.type == "negative-control" and q.paired_positive:
            pos = qmap.get(q.paired_positive)
            if pos is None:
                continue
            pos_sims = dict(sim_by_id.get(pos.id, []))
            # lowest similarity among the paired positive's TRUE positives
            true_pos_sims = [pos_sims[c] for c in pos.relevant if c in pos_sims]
            if not true_pos_sims:
                continue
            floor = min(true_pos_sims)
            ctrl_sims = sim_by_id.get(q.id, [])
            # a control chunk that is a known corpus chunk AND outranks the floor
            offenders = [c for (c, s) in ctrl_sims if s > floor and c.startswith("c-")]
            if offenders:
                neg_control_violations.append(
                    f"{q.id}: control chunk(s) {offenders[:3]} outrank lowest "
                    f"true positive of {pos.id} (sim>{floor:.4f})"
                )

    # Second pass: latency (p50/p95 over repeated runs of the non-control set).
    timed = [q for q in queries if q.type not in ("negative-control", "gate-control")]
    for _ in range(latency_repeats):
        for q in timed:
            t0 = time.perf_counter()
            sub.query(q.query, top_k=q.top_k, source_tier_max=q.source_tier_max,
                      policy_tag=q.policy_tag)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    try:
        sub.close()
    except Exception:
        pass

    return _aggregate(
        kind, per_query, latencies_ms, build_ms,
        vss_active=vss_active, gate_leak=gate_leak,
        neg_control_violations=neg_control_violations,
    )


def _aggregate(
    kind: str,
    per_query: list[QueryResult],
    latencies_ms: list[float],
    build_ms: float,
    *,
    vss_active: bool | None,
    gate_leak: str | None,
    neg_control_violations: list[str],
) -> dict:
    scored = [q for q in per_query if q.recall is not None]
    lb = [q for q in scored if q.load_bearing]
    nlb = [q for q in scored if not q.load_bearing]

    def _mean(rows: list[QueryResult]) -> float | None:
        vals = [q.recall for q in rows if q.recall is not None]
        return round(statistics.fmean(vals), 4) if vals else None

    # per-domain recall (§1 clause 1)
    domains: dict[str, list[QueryResult]] = {}
    for q in scored:
        domains.setdefault(q.domain, []).append(q)
    per_domain = {d: _mean(rows) for d, rows in sorted(domains.items())}

    return {
        "substrate": kind,
        "status": "measured",
        "vss_active": vss_active,
        "recall_at_5": {
            "pooled": _mean(scored),
            "load_bearing": _mean(lb),
            "non_load_bearing": _mean(nlb),
            "per_domain": per_domain,
        },
        "latency_ms": {
            "p50": round(_percentile(latencies_ms, 50), 4),
            "p95": round(_percentile(latencies_ms, 95), 4),
            "n_samples": len(latencies_ms),
        },
        "index_build_ms": round(build_ms, 3),
        "gate_9_0": {
            "held": gate_leak is None,
            "leak_query": gate_leak,
        },
        "negative_controls": {
            "rank_based_ok": not neg_control_violations,
            "violations": neg_control_violations,
        },
        "per_query": [
            {
                "id": q.id, "domain": q.domain, "load_bearing": q.load_bearing,
                "label_provenance": q.label_provenance, "recall_at_5": q.recall,
                "note": q.note,
            }
            for q in per_query
        ],
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_benchmark(
    substrates: list[str],
    *,
    fixture_path: Path | None = None,
    out_path: Path | None = None,
    latency_repeats: int = LATENCY_REPEATS,
    prefer_real_embedder: bool = True,
) -> dict:
    queries, meta = _load_fixture(fixture_path or _default_fixture_path())

    embedder: Any
    if prefer_real_embedder:
        embedder = _real_embedder_or_none() or HashEmbedding()
    else:
        embedder = HashEmbedding()
    embedder_name = getattr(embedder, "name", type(embedder).__name__)
    embedder_semantic = bool(getattr(embedder, "semantic", False))

    scratch = tempfile.mkdtemp(prefix="antiek-retrieval-bench-")
    db_path = os.path.join(scratch, "graph.duckdb")
    baseline_counts = seed_graph(db_path, embedder)

    reports = []
    for kind in substrates:
        reports.append(run_candidate(
            kind, db_path, queries, embedder, latency_repeats=latency_repeats,
        ))

    # §16: confirm the seed row counts are unchanged after all query runs.
    post_counts = row_counts(db_path)

    artifact = {
        "spike": "retrieval-substrate-spike",
        "generated_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "embedder": {
            "name": embedder_name,
            "dimension": getattr(embedder, "dimension", None),
            "semantic": embedder_semantic,
            "caveat": (
                "Real semantic embedder — paraphrase/conceptual recall is "
                "load-bearing." if embedder_semantic else
                "dim-16 hash stub — NO semantic structure. Paraphrase/conceptual "
                "recall is NON-LOAD-BEARING (measures index mechanics + speed, "
                "not ranking quality). Run under all-MiniLM-L6-v2 to lift this."
            ),
        },
        "fixture": {
            "path": str(fixture_path or _default_fixture_path()),
            "n_queries": len(queries),
            "source": meta.get("source", ""),
        },
        "seed_row_counts": baseline_counts,
        "post_run_row_counts": post_counts,
        "single_writer_held": baseline_counts == post_counts,
        "latency_repeats": latency_repeats,
        "candidates": reports,
    }

    if out_path is None:
        date = _dt.date.today().isoformat()
        out_path = Path(_REPO) / "benchmarks" / "out" / f"retrieval_spike_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    artifact["_artifact_path"] = str(out_path)
    return artifact


def _print_summary(artifact: dict) -> None:
    print("\nretrieval-substrate spike")
    print("=========================")
    emb = artifact["embedder"]
    print(f"embedder: {emb['name']} (dim {emb['dimension']}, semantic={emb['semantic']})")
    if not emb["semantic"]:
        print("  ! stub embedder — paraphrase/conceptual recall NON-LOAD-BEARING")
    print(f"fixture: {artifact['fixture']['n_queries']} queries")
    print(f"single-writer held (row counts unchanged): {artifact['single_writer_held']}")
    print(f"\n{'candidate':<14}{'recall@5(LB)':>14}{'p50 ms':>10}{'p95 ms':>10}{'build ms':>11}  gate")
    for c in artifact["candidates"]:
        if c.get("status", "").startswith("skipped"):
            print(f"{c['substrate']:<14}{'— skipped (no creds) —':>45}")
            continue
        lb = c["recall_at_5"]["load_bearing"]
        lat = c["latency_ms"]
        gate = "held" if c["gate_9_0"]["held"] else f"LEAK@{c['gate_9_0']['leak_query']}"
        print(f"{c['substrate']:<14}{(lb if lb is not None else '—'):>14}"
              f"{lat['p50']:>10}{lat['p95']:>10}{c['index_build_ms']:>11}  {gate}")
    print(f"\nartifact: {artifact.get('_artifact_path')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SPR-05 retrieval-substrate benchmark")
    ap.add_argument("--substrate", action="append", dest="substrates",
                    help="candidate kind (vss|brute_force|turbopuffer|ducklake); "
                         "repeatable. Default: vss")
    ap.add_argument("--fixture", default=None, help="path to query fixture YAML")
    ap.add_argument("--out", default=None, help="output artifact path")
    ap.add_argument("--latency-repeats", type=int, default=LATENCY_REPEATS)
    ap.add_argument("--no-real-embedder", action="store_true",
                    help="force the hash stub even if sentence-transformers is present")
    args = ap.parse_args(argv)

    substrates = args.substrates or ["vss"]
    try:
        artifact = run_benchmark(
            substrates,
            fixture_path=Path(args.fixture) if args.fixture else None,
            out_path=Path(args.out) if args.out else None,
            latency_repeats=args.latency_repeats,
            prefer_real_embedder=not args.no_real_embedder,
        )
    except FixtureTooSmall as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_summary(artifact)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
