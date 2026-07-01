"""Operator probe for OA-020 retrieval-time gating.

This command proves the deployed code path enforces the Sprint 18
retrieval-time gate by creating a synthetic DuckDB graph and running the real
``substrate.graph.search.search`` SQL. It never mutates the live graph. Passing
this probe supports OA-020, but OA-020 is not closed until the operator runs it
on the production VM and commits the decision evidence.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.graph.search import search

QUERY = "quantum"
RESTRICTED_DOCUMENT_ID = "doc-restricted"


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@dataclass(frozen=True)
class PolicyProbe:
    policy_tag: str
    returned_document_ids: list[str]
    restricted_visible: bool
    expected_restricted_visible: bool
    passed: bool


@dataclass(frozen=True)
class ProbeResult:
    status: str
    db_path: str
    restricted_document_id: str
    probes: list[PolicyProbe]
    does_not_close_oa020: bool = True


def seed_probe_db(db_path: Path) -> None:
    con = connect_write(str(db_path), purpose="retrieval_gate_probe_seed")
    try:
        init_database(con)
        embed = StubEmbedding()
        docs = [
            ("doc-public", "public_domain", "Open access paper on quantum"),
            ("doc-licensed", "opt_in_licensed", "Opt-in licensed publisher paper"),
            (
                RESTRICTED_DOCUMENT_ID,
                "restricted_pending_opt_in",
                "Restricted Big-Five book chunk on quantum",
            ),
            ("doc-legacy", None, "Legacy chunk with no content_class"),
        ]
        for doc_id, content_class, text in docs:
            con.execute(
                """
                INSERT INTO documents (
                    document_id, title, source_tier, document_type, content_class
                ) VALUES (?, ?, 2, 'paper', ?)
                """,
                [doc_id, f"Title for {doc_id}", content_class],
            )
            con.execute(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, chunk_index, text, embedding, token_count
                ) VALUES (?, ?, 0, ?, ?, 10)
                """,
                [f"chunk-{doc_id}", doc_id, text, embed.encode(text)],
            )
    finally:
        con.close()


def _document_ids(results: dict[str, object]) -> list[str]:
    rows = results.get("results")
    if not isinstance(rows, list):
        return []
    doc_ids: list[str] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("document_id"), str):
            doc_ids.append(row["document_id"])
    return doc_ids


def run_probe(db_path: Path) -> ProbeResult:
    seed_probe_db(db_path)
    con = connect_write(str(db_path), purpose="retrieval_gate_probe_search")
    try:
        embed = StubEmbedding()
        probes: list[PolicyProbe] = []
        scenarios = [
            ("attribution_eligible", False),
            ("private_research", True),
            ("typo_value_should_not_unlock", False),
        ]
        for policy_tag, expected_visible in scenarios:
            results = search(
                con,
                QUERY,
                model=embed,
                top_k=10,
                policy_tag=policy_tag,
            )
            doc_ids = _document_ids(results)
            restricted_visible = RESTRICTED_DOCUMENT_ID in doc_ids
            probes.append(
                PolicyProbe(
                    policy_tag=policy_tag,
                    returned_document_ids=doc_ids,
                    restricted_visible=restricted_visible,
                    expected_restricted_visible=expected_visible,
                    passed=restricted_visible == expected_visible,
                )
            )
    finally:
        con.close()

    passed = all(probe.passed for probe in probes)
    return ProbeResult(
        status="PASS" if passed else "FAIL",
        db_path=str(db_path),
        restricted_document_id=RESTRICTED_DOCUMENT_ID,
        probes=probes,
    )


def format_text(result: ProbeResult) -> str:
    lines = [
        f"retrieval-gate-probe: {result.status}",
        f"db_path: {result.db_path}",
        f"restricted_document_id: {result.restricted_document_id}",
    ]
    for probe in result.probes:
        marker = "PASS" if probe.passed else "FAIL"
        visibility = "visible" if probe.restricted_visible else "excluded"
        expected = (
            "visible"
            if probe.expected_restricted_visible
            else "excluded"
        )
        lines.append(
            f"{marker} {probe.policy_tag}: restricted={visibility} "
            f"expected={expected}; returned={','.join(probe.returned_document_ids)}"
        )
    lines.append("oa020_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed a synthetic graph and verify the deployed retrieval-time gate. "
            "Does not touch the live graph or close OA-020 by itself."
        )
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Fresh DuckDB path to create. Defaults to a temporary probe DB.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.db_path is not None:
        db_path = args.db_path.expanduser().resolve()
        if db_path.exists():
            parser.error(f"--db-path must not already exist: {db_path}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        result = run_probe(db_path)
    else:
        with tempfile.TemporaryDirectory(prefix="antiek-oa020-gate-") as tmpdir:
            db_path = Path(tmpdir) / "probe.duckdb"
            result = run_probe(db_path)

    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
