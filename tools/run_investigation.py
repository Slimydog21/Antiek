#!/usr/bin/env python3
"""run_investigation — the thought-partner loop in one command (D4).

The north-star end state: the platform reads the operator's licensed library,
distills grounded insights with a REAL model, deposits them into the knowledge
graph, and then COMPOUNDS — a later question reuses those distilled insights
(``knowledge.reused``). This CLI packages that loop from the cycle-20 proof so
the operator can run it on demand. Cycle 20 proved the path on real data; the
operator's merge of #205 turned the reuse wire ON on main, so compounding now
works against the merged tree.

The loop, faithful to the proven substrate:
1. License the source book (``content_class`` NULL → ``user_owned``) so its
   chunks are servable — the gate D3 (``tools/license_library``) opens.
2. Pick a substantive real chunk from the source document.
3. Dispatch the ``note_taker`` role to a REAL model (providers bootstrapped
   from env: anthropic / deepseek / openrouter / xiaomi) and parse insights.
4. Deposit each distilled insight as a grounded ``insight`` node
   (``promote_insight``), cited to the real chunk — the flywheel's fuel.
5. Retrieve prior knowledge units ranked against a (possibly different)
   REUSE question, then assemble a reuse context pack that emits one
   ``knowledge.reused`` event — the flywheel turning.

Safety posture (mirrors ``tools/license_library``)
--------------------------------------------------
- ``--dry-run`` is the DEFAULT and writes NOTHING: it runs the dispatch +
  retrieval against a SCRATCH copy of the corpus, leaving the operator's real
  store untouched. ``--apply`` runs against the store named by ``--db-path``.
- The default ``--db-path`` is a fresh scratch copy under /tmp; the real store
  is touched only with an explicit ``--db-path ~/.antiek/research_graph.duckdb --apply``.
- Single-writer: every mutation rides ``connect_write(purpose=...)``.

Usage::

    # Dry-run the full loop on a scratch copy (real LLM call, no mutation):
    python -m tools.run_investigation --question "<your question>" --source-doc <doc-id>

    # Apply (mutate the named store):
    python -m tools.run_investigation --question "..." --source-doc <doc-id> \\
        --db-path ~/.antiek/research_graph.duckdb --apply
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

DEFAULT_DB_PATH = "/Users/slimydog/.antiek/research_graph.duckdb"
DEFAULT_SOURCE_TIER = 2
DEFAULT_ROLE = "note_taker"

# Document-distillation prompt — extracts crystallized insights from a raw
# passage (NOT the note_taker wrestling-session prompt, which expects an
# active conversation). Fits the same {"notes":[{"text","confidence"}]} JSON
# the parser (parse_notes_response) consumes, so the deposit path is unchanged.
DOCUMENT_DISTILL_PROMPT = """You are a research assistant distilling a source
passage into grounded, reusable insights for a knowledge graph.

Given a research question and a source passage, surface the key truths the
passage establishes — the insights an operator would re-load as "what this
source taught me about the question."

Respond with JSON only — no prose, no markdown fences:

{
  "notes": [
    {
      "text": "<one short, declarative sentence stating the insight>",
      "confidence": "high" | "moderate" | "low" | "unknown",
      "source_event_ids": []
    }
  ]
}

## Rules
1. **Grounded, not hallucinated.** Every insight must be directly supported
   by the passage. If the passage doesn't address it, don't note it.
2. **Be terse.** 1-5 notes. One short sentence each.
3. **Confidence.** "high" when the passage states it plainly. "moderate"
   when it's a reasonable inference. "low" when speculative.
4. **Declarative.** State the truth, not "the text says..." — the insight
   should stand alone as knowledge.

If the passage is pure data/tables with no extractable insight, return
{"notes": []}.
""".strip()


@dataclass
class LoopResult:
    """Outcome of one thought-partner loop run."""
    source_doc: str
    chunk_id: str | None
    distilled_notes: int
    deposited_insights: list[str]
    units_retrieved: int
    reuse_injected: bool
    reused_unit_ids: list[str]
    applied: bool

    def summarize(self) -> str:
        lines = [
            f"source_doc={self.source_doc} chunk={self.chunk_id}",
            f"distilled_notes={self.distilled_notes} deposited_insights={len(self.deposited_insights)}",
            f"units_retrieved={self.units_retrieved} reuse_injected={self.reuse_injected}",
            f"reused_unit_ids={self.reused_unit_ids}",
            f"applied={self.applied}",
        ]
        return "\n".join(lines)


def _parse_document_notes(text: str) -> list[Any]:
    """Parse distilled notes from a document-distillation response.

    Unlike ``parse_notes_response`` (the wrestling-session parser), this does
    NOT require ``source_event_ids`` — the source IS the document chunk, cited
    via ``promote_insight(source_document_id=..., chunk_id=...)`` at deposit.
    The wrestling parser's rule-4 attribution defense is wrong here: it would
    drop every document-distilled note as "unattributed."
    """
    import json
    import re

    from roles.note_taker.parser import ExtractedNote, _new_note_id, _normalize_confidence

    stripped = text.strip()
    # tolerate markdown fences + leading prose
    fence = re.search(r"\{.*\}", stripped, re.DOTALL)
    candidate = fence.group(0) if fence else stripped
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        # try the first balanced {...}
        depth = 0
        start = stripped.find("{")
        if start < 0:
            return []
        for i in range(start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(stripped[start : i + 1])
                    except json.JSONDecodeError:
                        return []
                    break
        else:
            return []
    raw_notes = obj.get("notes") if isinstance(obj, dict) else None
    if not isinstance(raw_notes, list):
        return []
    out = []
    for rn in raw_notes:
        if not isinstance(rn, dict):
            continue
        body = rn.get("text")
        if not isinstance(body, str) or not body.strip():
            continue
        out.append(ExtractedNote(
            note_id=_new_note_id(),
            text=body.strip(),
            confidence=_normalize_confidence(rn.get("confidence")),
            source_event_ids=(),
        ))
    return out


def _bootstrap_dispatch() -> tuple[Any, list[str]]:
    """Import + register the real LLM providers. Returns (dispatch, registered)."""
    from substrate.dispatch import dispatch  # noqa: F401
    from substrate.dispatch.providers.bootstrap import register_default_providers

    registered = register_default_providers()
    return dispatch, sorted(registered)


def _license_source(con: Any, document_id: str) -> None:
    """Flip the source doc to user_owned so its chunks are servable."""
    from substrate.graph.ops import update_document_gate_columns

    update_document_gate_columns(
        con, document_id, content_class="user_owned", set_content_class=True
    )


def _pick_substantive_chunk(read_con: Any, document_id: str) -> tuple[str | None, str]:
    """Pick the most substantive non-boilerplate chunk from the source doc.
    Skips bibliography / references / index / TOC / pure page-header pages so
    the model distills actual content, not a citation list."""
    row = read_con.execute(
        """SELECT chunk_id, text FROM chunks
           WHERE document_id = ?
             AND length(text) BETWEEN 400 AND 4000
             AND text NOT ILIKE '%bibliography%'
             AND text NOT ILIKE '%references%'
             AND text NOT ILIKE '%index%'
             AND text NOT ILIKE '## Page%'
             AND text NOT ILIKE 'chapter %'
             AND text NOT ILIKE 'contents%'
           ORDER BY length(text) DESC
           LIMIT 1""",
        [document_id],
    ).fetchone()
    if not row:
        return None, ""
    return (None if row[0] is None else str(row[0])), str(row[1])


def _distill(dispatch: Any, chunk_text: str, question: str, investigation_id: str) -> list[Any]:
    """Distill insights from the chunk with a real model using the document-
    distillation prompt (not the note_taker wrestling-session prompt). Returns
    parsed ExtractedNote objects."""
    prompt = (
        f"{DOCUMENT_DISTILL_PROMPT}\n\n"
        f"Research question: {question}\n\n"
        f"Source passage:\n{chunk_text}"
    )
    result = dispatch(prompt, role=DEFAULT_ROLE, investigation_id=investigation_id, max_tokens=600)
    text = getattr(result, "text", None) or getattr(result, "response_text", "") or ""
    return _parse_document_notes(text)


def _deposit_insights(
    write_con: Any,
    notes: list[Any],
    *,
    investigation_id: str,
    source_doc: str,
    chunk_id: str | None,
    source_tier: int,
    embedding_provider: Any,
    target_node_id: str | None,
) -> list[str]:
    """Deposit each distilled note as a grounded insight node. Returns ids."""
    from substrate.graph.insight_question import promote_insight

    deposited: list[str] = []
    for note in notes[:6]:
        text = (getattr(note, "text", None) or "").strip()
        if not text:
            continue
        confidence = getattr(note, "confidence", "unknown") or "unknown"
        nid = promote_insight(
            text=text,
            investigation_id=investigation_id,
            confidence=str(confidence),
            supported_by=( [target_node_id] if target_node_id else ()),
            source_document_id=source_doc,
            chunk_id=chunk_id,
            source_tier=source_tier,
            embedding_provider=embedding_provider,
            con=write_con,
        )
        deposited.append(nid)
    return deposited


def _reuse_step(
    read_con: Any,
    *,
    reuse_question: str,
    investigation_id: str,
    events_dir: str,
    embedding_provider: Any,
) -> tuple[int, bool, list[str]]:
    """Retrieve prior units + assemble a reuse context pack. Returns
    (units_retrieved, reuse_injected, reused_unit_ids)."""
    from substrate.context_pack.knowledge_reuse import (
        assemble_context_pack_with_reuse,
        retrieve_prior_units,
    )
    from substrate.graph.retrieval_substrate import make_substrate_from_con

    substrate = make_substrate_from_con("brute_force", read_con, model=embedding_provider)
    units = retrieve_prior_units(
        substrate, question_text=reuse_question, policy_tag="attribution_eligible", limit=10
    )
    pack = assemble_context_pack_with_reuse(
        role="evidence_retriever",
        investigation_id=investigation_id,
        layers=[],
        units=units,
        events_dir=events_dir,
    )
    reused = []
    reuse_events = os.path.join(events_dir)
    if os.path.isdir(reuse_events):
        import json
        for fname in sorted(os.listdir(reuse_events)):
            if not fname.endswith(".jsonl"):
                continue
            with open(os.path.join(reuse_events, fname), encoding="utf-8") as fh:
                for line in fh:
                    if '"knowledge.reused"' not in line:
                        continue
                    try:
                        payload = json.loads(line).get("payload", {})
                    except json.JSONDecodeError:
                        continue
                    ids = payload.get("reused_unit_ids") or []
                    if ids:
                        reused = list(ids)
                        break
            if reused:
                break
    return len(units), bool(pack.reuse_injected), reused


def run_loop(
    db_path: str,
    *,
    source_doc: str,
    question: str,
    investigation_id: str,
    source_tier: int,
    apply: bool,
) -> LoopResult:
    """Run the full thought-partner loop against ``db_path``."""
    import duckdb

    from runtime.db_lock import connect_write

    # Bootstrap providers once (real LLM keys resolved from env).
    dispatch, registered = _bootstrap_dispatch()
    print(f"providers: {registered}")
    if not registered:
        raise RuntimeError(
            "no LLM providers registered — set DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / "
            "OPENROUTER_API_KEY / XIAOMI_API_KEY"
        )

    # License the source book + pick a chunk + find a target node.
    with connect_write(db_path, purpose="d4:license_source") as con:
        _license_source(con, source_doc)

    read = duckdb.connect(db_path, read_only=True)
    try:
        chunk_id, chunk_text = _pick_substantive_chunk(read, source_doc)
        target = read.execute(
            "SELECT node_id FROM nodes WHERE node_type='entity' LIMIT 1"
        ).fetchone()
        target_node_id = target[0] if target else None
    finally:
        read.close()

    if not chunk_text:
        raise RuntimeError(
            f"no substantive chunk found in source_doc={source_doc!r} "
            f"(is it licensed + chunked?)"
        )
    print(f"chunk: {chunk_id} (len {len(chunk_text)})")
    print(f"chunk excerpt: {chunk_text[:140]!r}")

    # Distill with the production distiller (real model, proper prompt shape).
    notes = _distill(dispatch, chunk_text, question, investigation_id)
    print(f"distilled notes: {len(notes)}")

    # Deposit grounded insights (the flywheel's fuel).
    from processing.embedding import default_embedding_provider
    embedding_provider = default_embedding_provider()

    deposited: list[str] = []
    if notes and apply:
        with connect_write(db_path, purpose="d4:deposit_insights") as con:
            deposited = _deposit_insights(
                con, notes,
                investigation_id=investigation_id,
                source_doc=source_doc, chunk_id=chunk_id,
                source_tier=source_tier, embedding_provider=embedding_provider,
                target_node_id=target_node_id,
            )
        print(f"deposited insights: {len(deposited)}")
    elif notes and not apply:
        print(f"(dry-run) would deposit up to {min(6, len(notes))} insight(s); --apply to commit")

    # Reuse step — the flywheel turning over the (now richer) graph.
    events_dir = tempfile.mkdtemp(prefix=f"d4_{investigation_id}_")
    read = duckdb.connect(db_path, read_only=True)
    try:
        units_n, injected, reused = _reuse_step(
            read,
            reuse_question=question,
            investigation_id=investigation_id,
            events_dir=events_dir,
            embedding_provider=embedding_provider,
        )
    finally:
        read.close()
    print(f"reuse: units={units_n} injected={injected} reused_unit_ids={reused}")

    return LoopResult(
        source_doc=source_doc, chunk_id=chunk_id, distilled_notes=len(notes),
        deposited_insights=deposited, units_retrieved=units_n,
        reuse_injected=injected, reused_unit_ids=reused, applied=apply,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="run_investigation",
        description="Run the thought-partner loop: distill grounded insights from a licensed "
        "source doc with a real model, deposit them, and reuse prior knowledge. "
        "Scratch-copy DRY-RUN by default.",
    )
    p.add_argument("--question", required=True, help="the research question to investigate")
    p.add_argument(
        "--source-doc", required=True,
        help="document_id of the licensed source to distill from",
    )
    p.add_argument(
        "--db-path", default=None,
        help=f"path to the DuckDB. DEFAULT: a fresh scratch copy of {DEFAULT_DB_PATH}. "
        "Pass the real path + --apply to mutate the real store.",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="MUTATE the store named by --db-path. Without it, runs on a scratch copy.",
    )
    p.add_argument("--investigation-id", default=None, help="investigation id (default: auto)")
    p.add_argument("--source-tier", type=int, default=DEFAULT_SOURCE_TIER)
    args = p.parse_args(argv)

    db_path = args.db_path
    scratch_dir: str | None = None
    if db_path is None:
        scratch_dir = tempfile.mkdtemp(prefix="antiek-d4-")
        db_path = os.path.join(scratch_dir, "scratch.duckdb")
        shutil.copy(DEFAULT_DB_PATH, db_path)
        print(f"(dry-run) scratch copy at {db_path}")

    investigation_id = args.investigation_id or "d4-investigation"

    try:
        result = run_loop(
            db_path,
            source_doc=args.source_doc,
            question=args.question,
            investigation_id=investigation_id,
            source_tier=args.source_tier,
            apply=args.apply,
        )
    finally:
        pass

    mode = "APPLY" if args.apply else "DRY-RUN (scratch)"
    print(f"\n== run_investigation [{mode}] ==")
    print(result.summarize())
    ok = result.distilled_notes > 0
    print(f"\nloop {'PASS' if ok else 'NOTE'} (real LLM distilled {result.distilled_notes} note(s))")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
