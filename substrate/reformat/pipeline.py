"""The reformat pipeline (reformat-provenance SPR-01) — the ONLY writer of
provenance rows.

One pass: read the source through the GATED serve path
(serve_full_text_guarded — never a side channel) → split the served body
into deterministic paragraph blocks mapped through the unit-1 anchor-map
(chunk-relative spans in the normalized scalar space) → generate the
derived bites through the ONE dispatch path (substrate/dispatch's
``dispatch(prompt, role, …)`` — typed DispatchCall events, the operator's
lineup, the cost ledger) → write the derived document + the generation
record + EVERY bite's provenance in ONE bounded atomic write scope —
provenance captured AT WRITE TIME, never reconstructed.

THE BYTE-VERIFICATION: an author_verbatim bite's normalized text hash must
EQUAL its source span's — a mismatch is REJECTED and reclassed
llm_compressed with an audit event (never silently mislabeled; the DB CHECK
is the backstop). THE NOVELTY CEILING: null-source bites ("no direct
source") past the cap (default 20% of bites) flip the generation record's
honest mostly_generated flag + an audit event — the bites stay, honestly
marked (dropping them would hide the shape the operator asked to see).

REGENERATION STABILITY: blocks derive deterministically from the source's
chunks (order + offsets), and bite ordinals follow the generator's per-block
order — the same prompt+source+model reproduces the same ordinals and
classes; every run is a NEW generation with its own record (never an
in-place overwrite). The generator itself is the injectable seam (the
daemon's SpawnFn precedent — mechanics proven with a deterministic fixture
generator; the real one rides dispatch).

BORN PROVISIONAL: the derived document registers through the rights
chokepoint (register_source_document, deny-by-default) with the parent's
content_class inherited — a withheld source's derived asset stays
owner-only under the same gates — and carries its lineage
(derived_from_document_id in metadata) + the generation record. It is
reviewable, never library-blessed at birth ("officially fork" is unit 5's
promotion path, SPR-02's flow).

Audit events are metadata-only (counts and classes — NEVER bite text) on
the SOURCE document's reading thread (the anchors' _audit precedent).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.anchor_map import build_anchor_map
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.event_log import log_event
from substrate.feedback.domain import normalize_node_text
from substrate.provenance.store import (
    BiteRow,
    GenerationRecordRow,
    ProvenanceStore,
    make_bite_id,
    mint_generation_id,
    text_sha256,
)

#: The null-source novelty ceiling (the spec's value): past it, the asset
#: reads honestly as mostly generated.
NOVELTY_CEILING_SHARE = 0.20

_WS_PARAGRAPHS = re.compile(r"\n{2,}")


class ReformatError(RuntimeError):
    """An honest pipeline refusal (a gated source, a malformed generation,
    a bite that can't be classed honestly)."""


@dataclass(frozen=True, slots=True)
class SourceBlock:
    """One paragraph of the served source body, mapped to its unit-1 anchor
    payload into the CORE document (chunk id + chunk-relative scalars)."""

    index: int
    text: str  # normalized — the substrate's own scalar space
    chunk_id: str
    start_scalar: int
    end_scalar: int

    @property
    def anchor_ref(self) -> dict[str, Any]:
        """The unit-1 anchor payload shape (chunk-relative, normalized)."""
        return {
            "node_id": self.chunk_id,
            "start_scalar": self.start_scalar,
            "end_scalar": self.end_scalar,
        }


@dataclass(frozen=True, slots=True)
class GeneratedBite:
    """The generator's output contract: the derived bite's text, its
    DECLARED class (the pipeline VERIFIES — a declaration is never trusted),
    the source blocks it derives from (indices; null only for an honest
    no-direct-source bite), and the investigation id when
    research_supplemented."""

    text: str
    contribution_class: str
    source_block_indices: tuple[int, ...] | None
    investigation_id: str | None = None


#: The generator seam (the daemon's SpawnFn precedent): (prompt, blocks,
#: params) → the bites. The REAL one rides the one dispatch path; tests
#: inject a deterministic fixture generator.
GenerateFn = Callable[[str, list[SourceBlock], dict[str, Any]], list[GeneratedBite]]


@dataclass(frozen=True, slots=True)
class ReformatResult:
    generation_id: str
    derived_document_id: str
    bite_ids: list[str]
    contribution_classes: list[str]
    mostly_generated: bool
    reclassed_verbatim: int
    null_source_share: float


def _source_blocks(con: Any, document_id: str, served_text: str) -> list[SourceBlock]:
    """The served body as deterministic paragraph blocks, chunk-mapped
    through the unit-1 anchor-map (the SAME normalized scalar space the
    anchors use — a bite's span and an island's anchor agree by
    construction)."""
    anchor_map = build_anchor_map(con, document_id=document_id, served_text=served_text)
    body = normalize_node_text(served_text)
    out: list[SourceBlock] = []
    index = 0
    for chunk in anchor_map.chunks:
        chunk_text = body[chunk.body_start : chunk.body_end]
        # Split on paragraph separators of ANY length (a run of \n{2,}),
        # advancing by the separator's ACTUAL span so later blocks' scalars
        # never drift — a citation must slice exactly the text it names.
        parts: list[tuple[int, str]] = []
        last = 0
        for separator in _WS_PARAGRAPHS.finditer(chunk_text):
            parts.append((last, chunk_text[last : separator.start()]))
            last = separator.end()
        parts.append((last, chunk_text[last:]))
        for start, raw in parts:
            stripped = raw.strip()
            if not stripped or stripped.startswith("## "):
                continue
            lead = len(raw) - len(raw.lstrip())
            out.append(
                SourceBlock(
                    index=index,
                    text=stripped,
                    chunk_id=chunk.chunk_id,
                    start_scalar=start + lead,
                    end_scalar=start + lead + len(stripped),
                )
            )
            index += 1
    return out


def _dispatch_generate(
    prompt: str, blocks: list[SourceBlock], params: dict[str, Any]
) -> list[GeneratedBite]:
    """The REAL generator: ONE dispatch call (the single entry — the typed
    DispatchCall event, the lineup, the cost ledger) with a STRICT JSON
    contract; a malformed generation is an honest refusal, never a guess."""
    from substrate.dispatch.router import dispatch

    schema_hint = (
        '[{"text": "…", "contribution_class": "author_verbatim|llm_compressed|'
        'llm_expanded|research_supplemented", "source_block_indices": [0], '
        '"investigation_id": null}]'
    )
    block_listing = "\n".join(f"[{b.index}] {b.text}" for b in blocks)
    result = dispatch(
        (
            f"{prompt}\n\nSource blocks:\n{block_listing}\n\n"
            f"Return ONLY a JSON array of derived bites in this shape: {schema_hint}"
        ),
        "reformat",
        investigation_id=str(params.get("thread_id") or "reformat-pipeline"),
        model_override=params.get("model"),
    )
    try:
        raw = json.loads(result.text)
    except json.JSONDecodeError as e:
        raise ReformatError(
            f"the generation returned unparseable output: {e}"
        ) from e
    if not isinstance(raw, list):
        raise ReformatError("the generation returned a non-array payload")
    bites: list[GeneratedBite] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ReformatError("a generated bite lacks its text")
        indices = item.get("source_block_indices")
        bites.append(
            GeneratedBite(
                text=item["text"],
                contribution_class=str(item.get("contribution_class") or ""),
                source_block_indices=(
                    None
                    if indices is None
                    else tuple(int(i) for i in indices)
                ),
                investigation_id=(
                    None
                    if item.get("investigation_id") is None
                    else str(item["investigation_id"])
                ),
            )
        )
    return bites


def reformat_document(
    db_path: str,
    *,
    owner_user_id: str,
    source_document_id: str,
    prompt: str,
    mode: str = "time_window",
    model: str = "operator-default",
    params: dict[str, Any] | None = None,
    generate_fn: GenerateFn | None = None,
    events_dir: str | None = None,
) -> ReformatResult:
    """Reformat one source document by prompt. THE writer of provenance.
    Never raises on the lawful refusal paths without an honest error class;
    never touches the source document."""
    if not prompt.strip():
        raise ReformatError("an empty prompt reformats nothing")
    if mode not in ("time_window", "themes"):
        raise ReformatError(f"unknown reformat mode: {mode}")
    params = dict(params or {})
    generate = generate_fn or _dispatch_generate
    # Minted EARLY: the generation's dispatch events carry the thread id
    # (reformat:{generation_id}) — the engagement that stays in the pane.
    generation_id = mint_generation_id()
    params.setdefault("thread_id", f"reformat:{generation_id}")

    # 1. The gated read — the ONLY way source text enters the pipeline.
    rcon = connect_read(db_path)
    try:
        source = rcon.execute(
            "SELECT title, content_class FROM documents WHERE document_id = ? LIMIT 1",
            [source_document_id],
        ).fetchone()
        if source is None:
            raise ReformatError(f"source document not found: {source_document_id}")
        served = serve_full_text_guarded(rcon, source_document_id, owner=True)
        if served.full_text is None:
            raise ReformatError(
                f"the source's body is not served even to its owner "
                f"({source_document_id}) — nothing to reformat"
            )
        blocks = _source_blocks(rcon, source_document_id, served.full_text)
        if not blocks:
            raise ReformatError("the served source has no paragraph blocks")
        source_title = None if source[0] is None else str(source[0])
        source_content_class = None if source[1] is None else str(source[1])
    finally:
        rcon.close()

    # 2. Generate (the dispatch path by default). No lock held across the
    #    LLM call — the arXiv lesson.
    bites = generate(prompt, blocks, params)

    # 3. Verify + class honestly, then write in ONE bounded atomic scope.
    by_index = {b.index: b for b in blocks}
    derived_document_id = f"drv-{generation_id[4:]}"

    out_bites: list[BiteRow] = []
    derived_paragraphs: list[str] = []
    reclassed = 0
    null_source = 0
    for ordinal, bite in enumerate(bites):
        text = normalize_node_text(bite.text).strip()
        if not text:
            continue  # an empty bite is dropped honestly (never a blank row)
        declared = bite.contribution_class
        indices = bite.source_block_indices
        source_refs: list[str] | None = None
        source_sha: str | None = None
        if indices:
            try:
                span_blocks = [by_index[i] for i in indices]
            except KeyError as e:
                raise ReformatError(
                    f"a bite refs source block {e} which does not exist"
                ) from e
            source_refs = [
                json.dumps(b.anchor_ref, sort_keys=True) for b in span_blocks
            ]
            source_sha = text_sha256(
                "\n\n".join(b.text for b in span_blocks)
                if len(span_blocks) > 1
                else span_blocks[0].text
            )
        derived_sha = text_sha256(text)

        cls = declared
        if declared == "author_verbatim":
            # BYTE-VERIFIED or reclassed — never trusted by declaration.
            if source_sha is not None and source_sha == derived_sha:
                pass  # proven
            else:
                cls = "llm_compressed"  # the honest reclass; the span hash
                reclassed += 1  # stands as the evidence of the mismatch
        elif declared in ("llm_compressed", "llm_expanded"):
            if not indices:
                cls = declared  # allowed but honestly sourceless
        elif declared == "research_supplemented":
            if not bite.investigation_id:
                raise ReformatError(
                    "a research_supplemented bite carries no investigation id"
                )
        else:
            raise ReformatError(f"unknown contribution class: {declared!r}")

        if not source_refs:
            null_source += 1
        out_bites.append(
            BiteRow(
                bite_id=make_bite_id(
                    generation_id, ordinal, text, cls, source_refs or []
                ),
                generation_id=generation_id,
                ordinal=ordinal,
                contribution_class=cls,
                source_refs=None if source_refs is None else tuple(source_refs),
                investigation_id=bite.investigation_id,
                derived_text_sha256=derived_sha,
                source_span_sha256=source_sha,
            )
        )
        derived_paragraphs.append(text)

    if not out_bites:
        raise ReformatError("the generation produced no usable bites")

    null_share = null_source / len(out_bites)
    mostly_generated = null_share > NOVELTY_CEILING_SHARE

    with connect_write(db_path, purpose="reformat/write-derived") as con, con.transaction():
        # The derived document: registered through the rights chokepoint
        # with the parent's rights posture inherited (deny-by-default).
        from substrate.graph.ops import insert_document
        from substrate.rights.register import SourceKind, register_source_document

        insert_document(
            con,
            document_id=derived_document_id,
            source_tier=1,
            document_type="derived",
            title=f"{source_title or 'A document'} — reformatted",
            raw_text="\n\n".join(derived_paragraphs),
            content_class=source_content_class,
            owner_user_id=owner_user_id,
            metadata={
                "derived_from_document_id": source_document_id,
                "generation_id": generation_id,
                "provisional": True,
            },
            on_conflict="ignore",
        )
        register_source_document(
            con,
            document_id=derived_document_id,
            source_kind=SourceKind.USER_CONTENT,
            content_class=source_content_class,
            run_self_check=False,
        )
        # One chunk per bite — the derived document paginates bite-aligned.
        for i, row in enumerate(out_bites):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    f"{derived_document_id}-b{row.ordinal}",
                    derived_document_id,
                    i,
                    f"Bite {row.ordinal + 1}",
                    derived_paragraphs[i],
                    len(derived_paragraphs[i].split()),
                ],
            )
        ProvenanceStore().record_generation(
            con,
            record=GenerationRecordRow(
                generation_id=generation_id,
                owner_user_id=owner_user_id,
                source_document_id=source_document_id,
                derived_document_id=derived_document_id,
                prompt=prompt,
                model=str(params.get("model") or model),
                params_json=json.dumps({"mode": mode, **params}, sort_keys=True),
                mostly_generated=mostly_generated,
                created_at="",  # the DDL default stamps it
            ),
            bites=out_bites,
        )

    # 4. The audit events — metadata-only, on the SOURCE's reading thread
    #    (the anchors' _audit precedent; counts and classes, never text).
    if reclassed:
        log_event(
            f"read-{source_document_id}",
            "reformat.verbatim_reclassified",
            payload={
                "generation_id": generation_id,
                "reclassed": reclassed,
                "document_id": source_document_id,
            },
            document_id=source_document_id,
            events_dir=events_dir,
        )
    if mostly_generated:
        log_event(
            f"read-{source_document_id}",
            "reformat.novelty_ceiling",
            payload={
                "generation_id": generation_id,
                "null_source_share": round(null_share, 4),
                "ceiling": NOVELTY_CEILING_SHARE,
                "bites": len(out_bites),
                "document_id": source_document_id,
            },
            document_id=source_document_id,
            events_dir=events_dir,
        )

    return ReformatResult(
        generation_id=generation_id,
        derived_document_id=derived_document_id,
        bite_ids=[b.bite_id for b in out_bites],
        contribution_classes=[b.contribution_class for b in out_bites],
        mostly_generated=mostly_generated,
        reclassed_verbatim=reclassed,
        null_source_share=null_share,
    )
