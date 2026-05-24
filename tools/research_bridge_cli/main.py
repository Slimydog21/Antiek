"""CLI entry point for the Antiek Deep Research Bridge.

Subcommands:

  list, show, paste, detect, extract, find-gaps, gaps-show,
  gaps-list, signal, would-run, eval-precision, dogfood-report

Exit codes:
  0  success
  2  invalid usage
  3  paste rejected
  4  not found
  5  extractor / gap-finder runtime error
  6  S3 gate failed (would-run % below floor / eval below floor)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

import duckdb

from runtime.db_lock import connect_write
from substrate.research_bridge import (
    EXTRACTOR_VERSION,
    KNOWN_SOURCES,
    PASTE_DOCUMENT_TYPE,
    ExtractorError,
    GapFinderError,
    PasteEmptyError,
    PasteTooLargeError,
    detect_source,
    ensure_research_bridge_initialized,
    extract_paste,
    find_gaps,
    ingest_paste,
    list_gap_runs,
    list_insights,
    list_open_questions,
    list_paste_events,
    read_gap_run,
    record_prompt_answer,
    record_prompt_signal,
    would_run_percentage,
)


# ---------------------------------------------------------------------------
# Paste-side subcommands
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        where_sql = ""
        params: list = []
        if args.source:
            where_sql = "WHERE rp.source = ?"
            params.append(args.source)
        params.append(args.limit)
        rows = con.execute(
            f"""
            SELECT rp.document_id, rp.source, rp.source_confidence,
                   rp.paste_byte_length, rp.operator_label, rp.session_id,
                   rp.pasted_at, d.title
            FROM research_pastes rp
            JOIN documents d ON d.document_id = rp.document_id
            {where_sql}
            ORDER BY rp.pasted_at DESC LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        con.close()
    if args.json:
        print(json.dumps([
            {
                "document_id": r[0], "source": r[1], "source_confidence": r[2],
                "paste_byte_length": r[3], "operator_label": r[4],
                "session_id": r[5], "pasted_at": str(r[6]), "title": r[7],
            } for r in rows
        ], indent=2))
        return 0
    if not rows:
        print("(no pastes yet)")
        return 0
    print(f"{'DOCUMENT_ID':<24} {'SOURCE':<11} {'CONF':>4} {'BYTES':>7}  "
          f"{'PASTED_AT':<19}  LABEL")
    for r in rows:
        doc_short = r[0][:22] + "…" if len(r[0]) > 22 else r[0]
        label = (r[4] or "")[:32]
        print(
            f"{doc_short:<24} {r[1]:<11} {r[2]:>4.2f} {r[3]:>7}  "
            f"{str(r[6])[:19]:<19}  {label}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        row = con.execute(
            """
            SELECT rp.document_id, rp.source, rp.source_confidence,
                   rp.raw_sha256, rp.paste_byte_length, rp.parser_version,
                   rp.operator_label, rp.session_id, rp.pasted_at,
                   d.title, d.raw_text,
                   (SELECT COUNT(*) FROM chunks c WHERE c.document_id = rp.document_id)
            FROM research_pastes rp
            JOIN documents d ON d.document_id = rp.document_id
            WHERE rp.document_id = ?
            """,
            [args.document_id],
        ).fetchone()
        if row is None:
            print(f"paste not found: {args.document_id}", file=sys.stderr)
            return 4
        events = list_paste_events(con, document_id=args.document_id, limit=50)
    finally:
        con.close()
    if args.json:
        print(json.dumps({
            "document_id": row[0], "source": row[1], "source_confidence": row[2],
            "raw_sha256": row[3], "paste_byte_length": row[4],
            "parser_version": row[5], "operator_label": row[6],
            "session_id": row[7], "pasted_at": str(row[8]),
            "title": row[9], "chunk_count": row[11], "raw_text": row[10],
            "events": [
                {"event_id": e.event_id, "occurred_at": str(e.occurred_at),
                 "paste_byte_length": e.paste_byte_length,
                 "source": e.source, "call_site": e.call_site}
                for e in events
            ],
        }, indent=2))
        return 0
    print(f"document_id:        {row[0]}")
    print(f"title:              {row[9] or '(no title)'}")
    print(f"source:             {row[1]} (confidence {row[2]:.2f})")
    print(f"raw_sha256:         {row[3]}")
    print(f"paste_byte_length:  {row[4]}")
    print(f"parser_version:     {row[5]}")
    print(f"operator_label:     {row[6] or '(none)'}")
    print(f"session_id:         {row[7] or '(none)'}")
    print(f"pasted_at:          {row[8]}")
    print(f"chunk_count:        {row[11]}")
    print()
    print(f"paste_events ({len(events)}):")
    for e in events:
        print(f"  {e.occurred_at}  {e.call_site:<18}  {e.event_id}")
    if args.with_raw:
        print()
        print("---raw_text begins---")
        sys.stdout.write(row[10] or "")
        if not (row[10] or "").endswith("\n"):
            sys.stdout.write("\n")
        print("---raw_text ends---")
    return 0


def _cmd_paste(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("error: stdin was empty", file=sys.stderr)
        return 3
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge_cli/paste") as con:
            result = ingest_paste(
                con, raw_text=raw,
                operator_label=args.label, session_id=args.session,
                source_override=args.source_override,
                source_tier=args.tier, call_site="cli",
            )
    except PasteTooLargeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except PasteEmptyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({
            "document_id": result.document_id,
            "source": result.source,
            "source_confidence": result.source_confidence,
            "raw_sha256": result.raw_sha256,
            "paste_byte_length": result.paste_byte_length,
            "chunk_count": len(result.chunk_ids),
            "per_source_scores": result.detection.per_source,
        }, indent=2))
    else:
        print(f"ingested: {result.document_id}")
        print(f"  source:           {result.source} (confidence {result.source_confidence:.2f})")
        print(f"  paste_byte_length:{result.paste_byte_length}")
        print(f"  chunks created:   {len(result.chunk_ids)}")
        if result.source == "other":
            print("  per-source scores:")
            for s, v in sorted(result.detection.per_source.items(), key=lambda kv: -kv[1]):
                print(f"    {s:<12} {v:.3f}")
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("error: stdin was empty", file=sys.stderr)
        return 3
    result = detect_source(raw)
    if args.json:
        print(json.dumps({
            "source": result.source, "confidence": result.confidence,
            "parser_version": result.parser_version,
            "per_source": result.per_source,
        }, indent=2))
    else:
        print(f"chosen source: {result.source} (confidence {result.confidence:.3f})")
        print(f"parser_version: {result.parser_version}")
        print("per-source scores:")
        for s, v in sorted(result.per_source.items(), key=lambda kv: -kv[1]):
            print(f"  {s:<12} {v:.3f}")
    return 0


# ---------------------------------------------------------------------------
# Extraction subcommands (SPR-02)
# ---------------------------------------------------------------------------


def _cmd_extract(args: argparse.Namespace) -> int:
    from substrate.research_bridge.llm_dispatch import build_dispatch_llm_callable
    llm = build_dispatch_llm_callable()
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge_cli/extract") as con:
            r = extract_paste(con, args.document_id, llm_callable=llm,
                              regenerate=args.regenerate)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    except ExtractorError as e:
        print(f"extractor error: {e}", file=sys.stderr)
        return 5
    if args.json:
        print(json.dumps({
            "extraction_id": r.extraction_id, "document_id": r.document_id,
            "extractor_version": r.extractor_version, "model_id": r.model_id,
            "status": r.status,
            "insights": [
                {"summary": i.summary, "quote": i.quote,
                 "quote_start_offset": i.quote_start_offset,
                 "quote_end_offset": i.quote_end_offset,
                 "llm_confidence": i.llm_confidence}
                for i in r.insights
            ],
            "open_questions": [
                {"summary": q.summary, "quote": q.quote,
                 "quote_start_offset": q.quote_start_offset,
                 "quote_end_offset": q.quote_end_offset,
                 "llm_confidence": q.llm_confidence}
                for q in r.open_questions
            ],
            "quote_drops": r.quote_drops,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
        }, indent=2))
        return 0
    print(f"extraction_id:    {r.extraction_id}")
    print(f"document_id:      {r.document_id}")
    print(f"status:           {r.status}")
    print(f"extractor_version:{r.extractor_version}")
    print(f"model_id:         {r.model_id}")
    print(f"input_tokens:     {r.input_tokens}")
    print(f"output_tokens:    {r.output_tokens}")
    print(f"cost_usd:         ${r.cost_usd:.4f}")
    print(f"quote_drops:      {r.quote_drops}")
    print()
    print(f"insights ({len(r.insights)}):")
    for i in r.insights:
        print(f"  [{i.llm_confidence:.2f}] {i.summary}")
        print(f"     ↳ {i.quote[:120]!r}")
    print()
    print(f"open_questions ({len(r.open_questions)}):")
    for q in r.open_questions:
        print(f"  [{q.llm_confidence:.2f}] {q.summary}")
        print(f"     ↳ {q.quote[:120]!r}")
    return 0


# ---------------------------------------------------------------------------
# Gap-finder subcommands (SPR-05)
# ---------------------------------------------------------------------------


def _cmd_find_gaps(args: argparse.Namespace) -> int:
    from substrate.research_bridge.llm_dispatch import build_dispatch_llm_callable
    llm = build_dispatch_llm_callable()
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge_cli/find_gaps") as con:
            r = find_gaps(
                con, scope_block_ids=args.document_ids,
                llm_callable=llm,
                operator_label=args.label, session_id=args.session,
            )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except GapFinderError as e:
        print(f"gap-finder error: {e}", file=sys.stderr)
        return 5
    if args.json:
        print(json.dumps({
            "run_id": r.run_id,
            "clusters": [
                {"cluster_id": c.cluster_id, "label": c.label,
                 "priority_rank": c.priority_rank, "rationale": c.rationale,
                 "question_ids": list(c.question_ids)}
                for c in r.clusters
            ],
            "prompts": [
                {"order_index": p.order_index, "cluster_id": p.cluster_id,
                 "target_provider": p.target_provider,
                 "prompt_text": p.prompt_text,
                 "expected_output_shape": p.expected_output_shape,
                 "depends_on_prior_order_index": p.depends_on_prior_order_index,
                 "rationale": p.rationale}
                for p in r.prompts
            ],
            "grounding_drops": r.grounding_drops,
            "total_input_tokens": r.total_input_tokens,
            "total_output_tokens": r.total_output_tokens,
            "total_cost_usd": r.total_cost_usd,
        }, indent=2))
        return 0
    print(f"run_id:           {r.run_id}")
    print(f"clusters:         {len(r.clusters)}")
    print(f"prompts:          {len(r.prompts)}")
    print(f"grounding_drops:  {r.grounding_drops}")
    print(f"input_tokens:     {r.total_input_tokens}")
    print(f"output_tokens:    {r.total_output_tokens}")
    print(f"cost_usd:         ${r.total_cost_usd:.4f}")
    print()
    for c in r.clusters:
        print(f"[cluster {c.priority_rank}] {c.label}")
        if c.rationale:
            print(f"    rationale: {c.rationale}")
    print()
    print("PROMPTS — in the order they should be run:")
    for p in r.prompts:
        print(f"--- prompt {p.order_index}  ({p.target_provider}) ---")
        if p.depends_on_prior_order_index is not None:
            print(f"depends on prompt #{p.depends_on_prior_order_index}")
        if p.expected_output_shape:
            print(f"expect: {p.expected_output_shape}")
        print(p.prompt_text)
        print()
    return 0


def _cmd_gaps_show(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        run, clusters, prompts = read_gap_run(con, args.run_id)
    finally:
        con.close()
    if run is None:
        print(f"gap run not found: {args.run_id}", file=sys.stderr)
        return 4
    if args.json:
        print(json.dumps({
            "run_id": run.run_id, "operator_label": run.operator_label,
            "session_id": run.session_id,
            "scope_block_ids": list(run.scope_block_ids),
            "scope_question_ids": list(run.scope_question_ids),
            "cluster_model_id": run.cluster_model_id,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
            "total_cost_usd": run.total_cost_usd,
            "created_at": str(run.created_at),
            "clusters": [
                {"cluster_id": c.cluster_id, "label": c.label,
                 "priority_rank": c.priority_rank, "rationale": c.rationale}
                for c in clusters
            ],
            "prompts": [
                {"prompt_id": p.prompt_id, "order_index": p.order_index,
                 "cluster_id": p.cluster_id,
                 "target_provider": p.target_provider,
                 "prompt_text": p.prompt_text,
                 "expected_output_shape": p.expected_output_shape,
                 "depends_on_prior_order_index": p.depends_on_prior_order_index,
                 "rationale": p.rationale}
                for p in prompts
            ],
        }, indent=2))
        return 0
    print(f"run_id:           {run.run_id}")
    print(f"operator_label:   {run.operator_label or '(none)'}")
    print(f"session_id:       {run.session_id or '(none)'}")
    print(f"created_at:       {run.created_at}")
    print(f"cluster_model:    {run.cluster_model_id}")
    print(f"clusters:         {len(clusters)}")
    print(f"prompts:          {len(prompts)}")
    print()
    for c in clusters:
        print(f"[cluster {c.priority_rank}] {c.label}  ({c.cluster_id})")
    print()
    for p in prompts:
        print(f"--- prompt {p.order_index}  ({p.target_provider})  {p.prompt_id} ---")
        print(p.prompt_text)
        print()
    return 0


def _cmd_gaps_list(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        runs = list_gap_runs(con, limit=args.limit, session_id=args.session)
    finally:
        con.close()
    if args.json:
        print(json.dumps([
            {
                "run_id": r.run_id, "operator_label": r.operator_label,
                "session_id": r.session_id,
                "scope_block_count": len(r.scope_block_ids),
                "question_count": len(r.scope_question_ids),
                "total_cost_usd": r.total_cost_usd,
                "created_at": str(r.created_at),
            } for r in runs
        ], indent=2))
        return 0
    if not runs:
        print("(no gap runs yet)")
        return 0
    print(f"{'RUN_ID':<24} {'SCOPE':>5} {'Q':>4} {'COST':>7}  {'CREATED':<19}  LABEL")
    for r in runs:
        rid = r.run_id[:22] + "…" if len(r.run_id) > 22 else r.run_id
        label = (r.operator_label or "")[:30]
        print(
            f"{rid:<24} {len(r.scope_block_ids):>5} {len(r.scope_question_ids):>4} "
            f"${r.total_cost_usd:>6.4f}  {str(r.created_at)[:19]:<19}  {label}"
        )
    return 0


def _cmd_signal(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge_cli/signal") as con:
            sid = record_prompt_signal(con, prompt_id=args.prompt_id, signal_type=args.type)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"signal_id: {sid}")
    return 0


def _cmd_would_run(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        would, total, pct = would_run_percentage(con, run_id=args.run_id)
    finally:
        con.close()
    if args.json:
        print(json.dumps({
            "would_run_count": would, "total_signalled": total,
            "percentage": pct, "run_id": args.run_id,
        }, indent=2))
        return 0
    scope = f"run {args.run_id}" if args.run_id else "all runs"
    print(f"would_run: {would}/{total} = {pct:.1%}  ({scope})")
    return 0 if pct >= 0.5 else 6


# ---------------------------------------------------------------------------
# Eval-precision (SPR-02 M5) + dogfood-report (SPR-06)
# ---------------------------------------------------------------------------


def _cmd_eval_precision(args: argparse.Namespace) -> int:
    from pathlib import Path
    from substrate.research_bridge.eval import (
        SubstringJudge, load_labelled_pastes, score_against_labels,
    )
    labels_path = Path(args.labels)
    try:
        labels = load_labelled_pastes(labels_path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    if not labels:
        print(f"no labelled pastes in {labels_path}", file=sys.stderr)
        return 4
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)

    def _extracted_for(doc_id: str):
        ins = list_insights(con, document_id=doc_id, version=EXTRACTOR_VERSION)
        q = list_open_questions(con, document_id=doc_id, version=EXTRACTOR_VERSION)
        return ([i.summary for i in ins], [x.summary for x in q])

    try:
        rep = score_against_labels(
            labels, extracted_for_doc=_extracted_for, judge=SubstringJudge,
        )
    finally:
        con.close()
    if args.json:
        print(json.dumps({
            "rows": [
                {
                    "document_id": row.document_id,
                    "operator_label": row.operator_label,
                    "insight_precision": row.insight_precision,
                    "insight_recall": row.insight_recall,
                    "insight_matched": row.insight_matched,
                    "insight_extracted": row.insight_extracted,
                    "insight_labelled": row.insight_labelled,
                    "question_precision": row.question_precision,
                    "question_recall": row.question_recall,
                    "question_matched": row.question_matched,
                    "question_extracted": row.question_extracted,
                    "question_labelled": row.question_labelled,
                } for row in rep.rows
            ],
            "aggregate": {
                "insight_precision": rep.insight_precision,
                "insight_recall": rep.insight_recall,
                "question_precision": rep.question_precision,
                "question_recall": rep.question_recall,
                "s3_gate_passed": rep.s3_gate_passed(),
            },
        }, indent=2))
        return 0 if rep.s3_gate_passed() else 6
    print(f"Eval against {len(rep.rows)} labelled pastes — judge={args.judge}")
    print()
    print(f"{'DOC':<22} {'INS P':>6} {'INS R':>6} {'Q P':>6} {'Q R':>6}  LABEL")
    for row in rep.rows:
        doc_id = row.document_id[:22]
        print(
            f"{doc_id:<22} "
            f"{row.insight_precision:>6.2f} {row.insight_recall:>6.2f} "
            f"{row.question_precision:>6.2f} {row.question_recall:>6.2f}  "
            f"{row.operator_label or ''}"
        )
    print()
    print(f"AGGREGATE  insights P={rep.insight_precision:.3f} R={rep.insight_recall:.3f}")
    print(f"AGGREGATE  questions P={rep.question_precision:.3f} R={rep.question_recall:.3f}")
    passed = rep.s3_gate_passed()
    print(f"S3 gate (question P >= 0.50): {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 6


def _cmd_dogfood_report(args: argparse.Namespace) -> int:
    db = ensure_research_bridge_initialized()
    con = duckdb.connect(db, read_only=True)
    try:
        n_pastes = con.execute("SELECT COUNT(*) FROM research_pastes").fetchone()[0]
        paste_by_source = dict(con.execute(
            "SELECT source, COUNT(*) FROM research_pastes GROUP BY source ORDER BY 2 DESC"
        ).fetchall())
        paste_bytes_total = con.execute(
            "SELECT COALESCE(SUM(paste_byte_length), 0) FROM research_pastes"
        ).fetchone()[0]
        ext_rows = con.execute(
            "SELECT status, COUNT(*), "
            "       COALESCE(SUM(input_tokens), 0), "
            "       COALESCE(SUM(output_tokens), 0), "
            "       COALESCE(SUM(cost_usd), 0.0), "
            "       COALESCE(SUM(insights_count), 0), "
            "       COALESCE(SUM(open_questions_count), 0), "
            "       COALESCE(SUM(quote_drops), 0) "
            "FROM research_paste_extractions GROUP BY status"
        ).fetchall()
        ext_by_status = {r[0]: {
            "count": int(r[1]),
            "input_tokens": int(r[2]), "output_tokens": int(r[3]),
            "cost_usd": float(r[4]),
            "insights_count": int(r[5]), "open_questions_count": int(r[6]),
            "quote_drops": int(r[7]),
        } for r in ext_rows}
        total_ext_cost = sum(d["cost_usd"] for d in ext_by_status.values())
        gap_summary = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_input_tokens), 0), "
            "       COALESCE(SUM(total_output_tokens), 0), "
            "       COALESCE(SUM(total_cost_usd), 0.0) "
            "FROM research_gap_runs"
        ).fetchone()
        n_gap_runs = int(gap_summary[0])
        gap_cost = float(gap_summary[3])
        n_prompts = con.execute("SELECT COUNT(*) FROM research_gap_prompts").fetchone()[0]
        would, total_sig, pct = would_run_percentage(con)
        n_answers = con.execute("SELECT COUNT(*) FROM research_gap_prompt_answers").fetchone()[0]
        per_session = con.execute(
            "SELECT COALESCE(session_id, '<none>') AS sid, COUNT(*) "
            "FROM research_pastes GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    finally:
        con.close()
    total_cost = total_ext_cost + gap_cost
    s3_floor = 0.60
    s3_pass = pct >= s3_floor and total_sig > 0
    lines: list[str] = []
    lines.append("# ADRB dogfood metrics")
    lines.append("")
    lines.append("Generated: substrate snapshot.")
    lines.append("")
    if total_sig == 0:
        lines.append("## S3 gate — INSUFFICIENT DATA")
        lines.append("No signals recorded yet. Run prompts + record 👍/👎 before "
                     "the verdict doc is meaningful.")
    elif s3_pass:
        lines.append("## S3 gate — PASS")
        lines.append(f"would_run % = **{pct:.1%}** ({would}/{total_sig} signalled "
                     f"prompts) ≥ {s3_floor:.0%} floor.")
    else:
        lines.append("## S3 gate — FAIL")
        lines.append(f"would_run % = **{pct:.1%}** ({would}/{total_sig} signalled "
                     f"prompts) < {s3_floor:.0%} floor.")
    lines.append("")
    lines.append("## Pastes")
    lines.append(f"- Total pastes: **{n_pastes}**")
    lines.append(f"- Total bytes pasted: {paste_bytes_total:,}")
    lines.append("- By source:")
    for src, n in paste_by_source.items():
        lines.append(f"  - `{src}`: {n}")
    lines.append("")
    lines.append("## Extractions")
    for status, d in ext_by_status.items():
        lines.append(
            f"- **{status}**: count={d['count']}  "
            f"insights={d['insights_count']}  "
            f"open_questions={d['open_questions_count']}  "
            f"quote_drops={d['quote_drops']}  "
            f"cost=${d['cost_usd']:.4f}  "
            f"input_tokens={d['input_tokens']:,}  "
            f"output_tokens={d['output_tokens']:,}"
        )
    if not ext_by_status:
        lines.append("- (no extractions recorded)")
    lines.append("")
    lines.append("## Gap-finder runs")
    lines.append(f"- Runs: **{n_gap_runs}**")
    lines.append(f"- Prompts generated: {n_prompts}")
    lines.append(f"- Operator answers pasted-back: {n_answers}")
    lines.append(f"- LLM cost: ${gap_cost:.4f}")
    lines.append("")
    lines.append("## Signals")
    if total_sig == 0:
        lines.append("- No signals recorded.")
    else:
        lines.append(f"- Signalled prompts: {total_sig}")
        lines.append(f"- 👍 would_run: {would}")
        lines.append(f"- 👎 skip: {total_sig - would}")
        lines.append(f"- would_run %: {pct:.1%}")
    lines.append("")
    lines.append("## Cost")
    lines.append(f"- Extraction LLM cost: ${total_ext_cost:.4f}")
    lines.append(f"- Gap-finder LLM cost: ${gap_cost:.4f}")
    lines.append(f"- **Total LLM cost: ${total_cost:.4f}**")
    lines.append("")
    lines.append("## Sessions (zero-engagement check)")
    lines.append("Sessions with `pastes=1` and no follow-up extractions / "
                 "gap runs likely indicate operator opened, did nothing, "
                 "and bounced. Cross-reference with operator-log.md.")
    lines.append("")
    lines.append("| session_id | pastes |")
    lines.append("|---|---|")
    for sid, n in per_session:
        lines.append(f"| `{sid}` | {n} |")
    report = "\n".join(lines) + "\n"
    if args.out:
        out_path = args.out
        if os.path.isdir(out_path):
            out_path = os.path.join(out_path, "dogfood_metrics.md")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"wrote {out_path}", file=sys.stderr)
    if args.json:
        print(json.dumps({
            "s3_gate_passed": s3_pass,
            "would_run_count": would, "total_signalled": total_sig,
            "would_run_percentage": pct,
            "n_pastes": int(n_pastes),
            "n_pastes_by_source": paste_by_source,
            "paste_bytes_total": int(paste_bytes_total),
            "extractions_by_status": ext_by_status,
            "n_gap_runs": n_gap_runs, "n_prompts": int(n_prompts),
            "n_answers": int(n_answers),
            "extraction_cost_usd": total_ext_cost,
            "gap_cost_usd": gap_cost, "total_cost_usd": total_cost,
        }, indent=2))
    elif not args.out:
        print(report)
    if total_sig == 0:
        return 0
    return 0 if s3_pass else 6


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_bridge_cli",
        description="Operator CLI for the Antiek Deep Research Bridge",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List recent pastes")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--source", choices=KNOWN_SOURCES, default=None)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Show full paste detail")
    p_show.add_argument("document_id")
    p_show.add_argument("--with-raw", action="store_true")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=_cmd_show)

    p_paste = sub.add_parser("paste", help="Ingest a paste from stdin")
    p_paste.add_argument("--label", default=None)
    p_paste.add_argument("--session", default=None)
    p_paste.add_argument("--source-override", choices=KNOWN_SOURCES, default=None)
    p_paste.add_argument("--tier", type=int, default=4, choices=range(1, 6))
    p_paste.add_argument("--json", action="store_true")
    p_paste.set_defaults(func=_cmd_paste)

    p_detect = sub.add_parser("detect", help="Run source detection on stdin; no DB write")
    p_detect.add_argument("--json", action="store_true")
    p_detect.set_defaults(func=_cmd_detect)

    p_extract = sub.add_parser("extract", help="Run extraction on one paste (real LLM call)")
    p_extract.add_argument("document_id")
    p_extract.add_argument("--regenerate", action="store_true")
    p_extract.add_argument("--json", action="store_true")
    p_extract.set_defaults(func=_cmd_extract)

    p_gaps = sub.add_parser("find-gaps", help="Run the gap-finder: cluster + emit cascade prompts")
    p_gaps.add_argument("document_ids", nargs="+")
    p_gaps.add_argument("--label", default=None)
    p_gaps.add_argument("--session", default=None)
    p_gaps.add_argument("--json", action="store_true")
    p_gaps.set_defaults(func=_cmd_find_gaps)

    p_gshow = sub.add_parser("gaps-show", help="Read one gap-finder run")
    p_gshow.add_argument("run_id")
    p_gshow.add_argument("--json", action="store_true")
    p_gshow.set_defaults(func=_cmd_gaps_show)

    p_glist = sub.add_parser("gaps-list", help="List recent gap-finder runs")
    p_glist.add_argument("--limit", type=int, default=20)
    p_glist.add_argument("--session", default=None)
    p_glist.add_argument("--json", action="store_true")
    p_glist.set_defaults(func=_cmd_gaps_list)

    p_sig = sub.add_parser("signal", help="Record a 👍/👎 signal on a gap prompt")
    p_sig.add_argument("prompt_id")
    p_sig.add_argument("--type", required=True, choices=["would_run", "skip"])
    p_sig.set_defaults(func=_cmd_signal)

    p_wr = sub.add_parser("would-run", help="Aggregate would-run % across signalled prompts")
    p_wr.add_argument("--run-id", default=None)
    p_wr.add_argument("--json", action="store_true")
    p_wr.set_defaults(func=_cmd_would_run)

    p_eval = sub.add_parser("eval-precision", help="Compute precision vs labels (SPR-06 S3 gate)")
    p_eval.add_argument("--labels", required=True)
    p_eval.add_argument("--judge", default="substring", choices=["substring"])
    p_eval.add_argument("--json", action="store_true")
    p_eval.set_defaults(func=_cmd_eval_precision)

    p_df = sub.add_parser("dogfood-report", help="Substrate dogfood metrics report (SPR-06)")
    p_df.add_argument("--out", default=None)
    p_df.add_argument("--json", action="store_true")
    p_df.set_defaults(func=_cmd_dogfood_report)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
