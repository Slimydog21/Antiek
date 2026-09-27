"""The reformat pipeline (reformat-provenance SPR-01) — the ONLY writer of
provenance rows.

One pass: read the source through the GATED serve path
(serve_full_text_guarded — never a side channel) → split the served body
into deterministic paragraph blocks mapped through the unit-1 anchor-map
(chunk-relative spans in the normalized scalar space) → generate the
derived bites through the ONE dispatch path (substrate/dispatch's
``dispatch(prompt, role, …)`` — typed DispatchCall events, the operator's
lineup, the cost ledger), one bounded call per window of blocks → write the
derived document + the generation record + EVERY bite's provenance in ONE
bounded atomic write scope — provenance captured AT WRITE TIME, never
reconstructed.

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

BOUNDED (LB-4a): a source longer than ``MAX_SOURCE_CHARS`` is refused, never
truncated; the rest is generated in windows of at most ``WINDOW_CHARS`` of
block text, one dispatch call each, with ``MAX_OUTPUT_TOKENS`` per call. The
generation record keeps the model; the provider, every DispatchCall event id
and the summed cost ride the book-asset provenance line and the in-memory
``GenerationOutput`` (main's generation_records carries no columns for them).
No per-owner spend cap exists for this path yet (the ACU gate meters
investigation starts, and the §1.13 daily cap is not built); that is a
recorded gap, not a silent one.

BORN PROVISIONAL, REGISTERED HONESTLY (LB-4a; THREAD-CONTRACT §1.11a): the
derived document is the reader view of a derivation. It registers with source
kind ``derived`` and inherits its core document's content class and IP holder,
so author words stay attributable and a private reading stays private; its
trust tier is the lowest, never higher than the source's, because generated
text is never primary evidence. The derived document's metadata binds those
facts as ``rights_basis {core_documents, most_restrictive_class, holder_set}``. A source
that is itself a derivation is refused: following a derivation chain is
LB-4b's recursion. It gets a ``book_assets`` row so the reader opens it, and it
stays out of the library listing while provisional. Serving it applies the
source's CURRENT gate (``substrate.books.serve``), and a source takedown takes
it down too (``substrate.books.takedown``).

Audit events are metadata-only (counts and classes — NEVER bite text) on
the SOURCE document's reading thread (the anchors' _audit precedent).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.anchor_map import build_anchor_map
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.constants import TIER_LOWEST
from substrate.event_log import log_event, trajectory
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

#: A source longer than this (normalized served characters) is refused, never
#: truncated: a reformat that silently drops the end of a book would misstate
#: what it was made from.
MAX_SOURCE_CHARS = 400_000
#: One generation call sees at most this many characters of block text; a
#: single block longer than this is its own window.
WINDOW_CHARS = 16_000
#: The output bound of one generation call.
MAX_OUTPUT_TOKENS = 4096
#: A window answering with more bites than this is malformed, not generous.
MAX_BITES_PER_WINDOW = 200

_WS_PARAGRAPHS = re.compile(r"\n{2,}")
#: The event-log storage names an investigation id may take (no path parts).
_SAFE_INVESTIGATION_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}")


class ReformatError(RuntimeError):
    """An honest pipeline refusal (a gated source, a malformed generation,
    a bite that can't be classed honestly)."""


class ReformatUnavailable(ReformatError):
    """The generator could not run: no dispatch route for the role, or every
    provider in the chain failed. Nothing was written."""


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


@dataclass(frozen=True, slots=True)
class GenerationOutput:
    """One generation call's bites plus who wrote them. The dispatch
    generator always returns this; an injected generator may return a bare
    bite list, in which case the record names the injected model."""

    bites: list[GeneratedBite]
    provider: str | None = None
    model: str | None = None
    dispatch_event_id: str | None = None
    cost_usd: float = 0.0


#: The generator seam (the daemon's SpawnFn precedent): (prompt, blocks of one
#: window, params) → the bites. The REAL one rides the one dispatch path; tests
#: inject a deterministic fixture generator.
GenerateFn = Callable[
    [str, list[SourceBlock], dict[str, Any]], "list[GeneratedBite] | GenerationOutput"
]


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


def _windows(blocks: list[SourceBlock]) -> list[list[SourceBlock]]:
    """Consecutive blocks grouped so each window carries at most
    ``WINDOW_CHARS`` of block text (a single longer block stands alone)."""
    windows: list[list[SourceBlock]] = []
    current: list[SourceBlock] = []
    size = 0
    for block in blocks:
        if current and size + len(block.text) > WINDOW_CHARS:
            windows.append(current)
            current, size = [], 0
        current.append(block)
        size += len(block.text)
    if current:
        windows.append(current)
    return windows


def _dispatch_generate(
    prompt: str, blocks: list[SourceBlock], params: dict[str, Any]
) -> GenerationOutput:
    """The REAL generator: ONE bounded dispatch call per window (the single
    entry — the typed DispatchCall event, the lineup, the cost ledger) with a
    STRICT JSON contract. A malformed generation is an honest refusal, never a
    guess; a missing route or a failed provider chain is ``ReformatUnavailable``."""
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import dispatch

    schema_hint = (
        '[{"text": "…", "contribution_class": "author_verbatim|llm_compressed|'
        'llm_expanded|research_supplemented", "source_block_indices": [0], '
        '"investigation_id": null}]'
    )
    block_listing = "\n".join(f"[{b.index}] {b.text}" for b in blocks)
    try:
        result = dispatch(
            (
                f"{prompt}\n\nSource blocks:\n{block_listing}\n\n"
                f"Return ONLY a JSON array of derived bites in this shape: {schema_hint}"
            ),
            "reformat",
            # The generation's attribution bucket (THREAD-CONTRACT §1.2): the
            # DispatchCall events land under it. It is never a thread id.
            investigation_id=str(params.get("attribution_bucket") or "reformat-pipeline"),
            max_tokens=MAX_OUTPUT_TOKENS,
        )
    except (KeyError, ProviderError) as e:
        raise ReformatUnavailable(f"reformat_generator_unavailable: {e}") from e
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
                source_block_indices=_block_indices(indices),
                investigation_id=(
                    None
                    if item.get("investigation_id") is None
                    else str(item["investigation_id"])
                ),
            )
        )
    return GenerationOutput(
        bites=bites,
        provider=result.provider,
        model=result.model,
        dispatch_event_id=result.event_id,
        cost_usd=float(result.cost_usd),
    )


def _block_indices(value: object) -> tuple[int, ...] | None:
    """A bite's source block references: null, or a list of non-negative
    integers. Anything else is malformed output and an honest refusal, never
    coerced: a float, a numeric string or a JSON true would otherwise become a
    definite reference to a block the model never named."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and all(
        type(i) is int and i >= 0 for i in value
    ):
        return tuple(value)
    raise ReformatError(
        f"malformed_source_block_indices: expected null or a list of "
        f"non-negative integers, got {value!r:.80}"
    )


def _check_research_investigation(
    investigation_id: str, owner_ids: frozenset[str], events_dir: str | None
) -> None:
    """A research_supplemented bite must cite an investigation that exists and
    is the requester's. A start event that names an owner must name one of
    ``owner_ids``; a house start that names none is accepted, because owner
    scoping of investigations is pre-multi-user work (THREAD-CONTRACT §1.15)."""
    if not _SAFE_INVESTIGATION_ID.fullmatch(investigation_id) or ".." in investigation_id:
        raise ReformatError(f"research_investigation_invalid: {investigation_id!r}")
    start = next(
        (
            row
            for row in trajectory(investigation_id, events_dir=events_dir)
            if row.get("action_type") == "investigation.start_requested"
        ),
        None,
    )
    if start is None:
        raise ReformatError(f"research_investigation_unknown: {investigation_id}")
    payload = start.get("payload")
    recorded = payload.get("owner_user_id") if isinstance(payload, dict) else None
    if recorded is not None and str(recorded) not in owner_ids:
        raise ReformatError(f"research_investigation_not_owned: {investigation_id}")


@dataclass(frozen=True, slots=True)
class _SourceRead:
    """What the gated read saw: the rights facts the derivative inherits and
    the body it was generated from. Compared whole at the write."""

    title: str | None
    content_class: str | None
    ip_holder_id: str | None
    full_text: str


def _gated_source_read(con: Any, source_document_id: str) -> _SourceRead:
    """The source through the binding gate, as its owner. Refuses a missing
    source, a derived source (chains are LB-4b) and a body the gate withholds."""
    row = con.execute(
        "SELECT title, content_class, ip_holder_id, document_type, "
        "json_extract_string(metadata, '$.derived_from_document_id') "
        "FROM documents WHERE document_id = ? LIMIT 1",
        [source_document_id],
    ).fetchone()
    if row is None:
        raise ReformatError(f"source document not found: {source_document_id}")
    if row[3] == "derived" or row[4]:
        raise ReformatError(
            "derived_source_unsupported: a reformatted document cannot be "
            "reformatted again until derivation chains are supported"
        )
    served = serve_full_text_guarded(con, source_document_id, owner=True)
    if served.full_text is None:
        raise ReformatError(
            f"the source's body is not served even to its owner "
            f"({source_document_id}) — nothing to reformat"
        )
    return _SourceRead(
        title=None if row[0] is None else str(row[0]),
        content_class=None if row[1] is None else str(row[1]),
        ip_holder_id=None if row[2] is None else str(row[2]),
        full_text=served.full_text,
    )


def _rights_basis(
    source_document_id: str, source_content_class: str | None, source_ip_holder_id: str | None
) -> dict[str, Any]:
    """The derivation's rights facts (THREAD-CONTRACT §1.11a). The core set
    is the one source: a derived source is refused upstream, so there is no
    chain to fold."""
    return {
        "core_documents": [source_document_id],
        "most_restrictive_class": source_content_class,
        "holder_set": [source_ip_holder_id] if source_ip_holder_id else [],
    }


def _as_output(produced: list[GeneratedBite] | GenerationOutput) -> GenerationOutput:
    return produced if isinstance(produced, GenerationOutput) else GenerationOutput(bites=list(produced))


def _joined(values: Iterable[str | None]) -> str | None:
    distinct = sorted({v for v in values if v})
    return ",".join(distinct) if distinct else None


def reformat_document(
    db_path: str,
    *,
    owner_user_id: str,
    source_document_id: str,
    prompt: str,
    mode: str = "time_window",
    model: str = "injected-generator",
    params: dict[str, Any] | None = None,
    generate_fn: GenerateFn | None = None,
    events_dir: str | None = None,
    research_owner_ids: Iterable[str] | None = None,
) -> ReformatResult:
    """Reformat one source document by prompt. THE writer of provenance.
    Never raises on the lawful refusal paths without an honest error class;
    never touches the source document.

    ``model`` names an injected generator that reports no identity of its
    own; the dispatch generator records the provider and model that actually
    answered. ``research_owner_ids`` are the requester's ids a cited
    investigation's start event may name (the route passes both the reader
    id and the verified-email owner); it defaults to ``owner_user_id``."""
    if not prompt.strip():
        raise ReformatError("an empty prompt reformats nothing")
    if mode not in ("time_window", "themes"):
        raise ReformatError(f"unknown reformat mode: {mode}")
    params = dict(params or {})
    generate = generate_fn or _dispatch_generate
    owner_ids = frozenset(research_owner_ids or ()) | {owner_user_id}
    # Minted EARLY: the generation's dispatch events land under its
    # attribution bucket (reformat:{generation_id}), never a thread id.
    generation_id = mint_generation_id()
    params.setdefault("attribution_bucket", f"reformat:{generation_id}")

    # 1. The gated read — the ONLY way source text enters the pipeline.
    rcon = connect_read(db_path)
    try:
        source = _gated_source_read(rcon, source_document_id)
        if len(normalize_node_text(source.full_text)) > MAX_SOURCE_CHARS:
            raise ReformatError(
                f"source_too_long: the source exceeds {MAX_SOURCE_CHARS} characters; "
                "reformat a part of it instead"
            )
        blocks = _source_blocks(rcon, source_document_id, source.full_text)
        if not blocks:
            raise ReformatError("the served source has no paragraph blocks")
    finally:
        rcon.close()
    source_title = source.title
    source_content_class = source.content_class
    source_ip_holder_id = source.ip_holder_id
    rights_basis = _rights_basis(source_document_id, source_content_class, source_ip_holder_id)

    # 2. Generate, one bounded call per window (the dispatch path by default).
    #    No lock held across the LLM calls — the arXiv lesson.
    bites: list[GeneratedBite] = []
    outputs: list[GenerationOutput] = []
    for window in _windows(blocks):
        output = _as_output(generate(prompt, window, params))
        if len(output.bites) > MAX_BITES_PER_WINDOW:
            raise ReformatError(
                f"a generation window returned {len(output.bites)} bites "
                f"(the bound is {MAX_BITES_PER_WINDOW})"
            )
        outputs.append(output)
        bites.extend(output.bites)

    # 3. Verify + class honestly, then write in ONE bounded atomic scope.
    by_index = {b.index: b for b in blocks}
    derived_document_id = f"drv-{generation_id[4:]}"

    out_bites: list[BiteRow] = []
    derived_paragraphs: list[str] = []
    reclassed = 0
    null_source = 0
    checked_investigations: set[str] = set()
    for ordinal, bite in enumerate(bites):
        text = normalize_node_text(bite.text).strip()
        if not text:
            continue  # an empty bite is dropped honestly (never a blank row)
        declared = bite.contribution_class
        indices = _block_indices(bite.source_block_indices)
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
            if bite.investigation_id not in checked_investigations:
                _check_research_investigation(bite.investigation_id, owner_ids, events_dir)
                checked_investigations.add(bite.investigation_id)
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
    recorded_model = _joined(o.model for o in outputs) or str(params.get("model") or model)
    recorded_provider = _joined(o.provider for o in outputs)
    event_ids = tuple(o.dispatch_event_id for o in outputs if o.dispatch_event_id)
    total_cost = sum(o.cost_usd for o in outputs)

    with connect_write(db_path, purpose="reformat/write-derived") as con, con.transaction():
        # The derived id is freshly minted; a row already carrying it is an
        # anomaly (a pre-seeded or collided id). Refuse the WHOLE write —
        # never attach chunks or a generation record to a foreign document
        # through insert-on-conflict's silent skip.
        collision = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1",
            [derived_document_id],
        ).fetchone()
        if collision is not None:
            raise ReformatError(
                f"derived document id collision: {derived_document_id} — "
                "nothing was written"
            )
        # The gate again, inside the write. No lock is held while the model
        # generates, so the source may have been taken down or reclassified
        # since step 1. Under the single writer a takedown either committed
        # before this transaction (refused here) or commits after it (and its
        # propagation finds this derivative), so no derivative is born with a
        # class its source no longer has.
        try:
            current = _gated_source_read(con, source_document_id)
        except ReformatError as e:
            raise ReformatError(
                f"source_changed_during_generation: {e} — nothing was written"
            ) from e
        if current != source:
            raise ReformatError(
                "source_changed_during_generation: the source's rights or text "
                "changed while the reformat was generated — nothing was written"
            )
        from substrate.books.model import upsert_book_asset
        from substrate.graph.ops import insert_document
        from substrate.rights.register import SourceKind, register_source_document

        insert_document(
            con,
            document_id=derived_document_id,
            source_tier=TIER_LOWEST,
            document_type="derived",
            title=f"{source_title or 'A document'} — reformatted",
            raw_text="\n\n".join(derived_paragraphs),
            content_class=source_content_class,
            ip_holder_id=source_ip_holder_id,
            owner_user_id=owner_user_id,
            metadata={
                "derived_from_document_id": source_document_id,
                "generation_id": generation_id,
                "source_content_class": source_content_class,
                "rights_basis": rights_basis,
                # LB-4a attribution, kept here because main's
                # generation_records carries no columns for it (Option C
                # keeps main's provenance schema/store).
                "generation_attribution": {
                    "provider": recorded_provider,
                    "dispatch_event_ids": list(event_ids),
                    "cost_usd": total_cost,
                },
                "provisional": True,
            },
            on_conflict="error",
        )
        register_source_document(
            con,
            document_id=derived_document_id,
            source_kind=SourceKind.DERIVED,
            content_class=source_content_class,
            ip_holder_id=source_ip_holder_id,
            run_self_check=False,
        )
        # The reader opens a document through its book_assets row; the
        # listing skips it while it is provisional (substrate.books.model).
        upsert_book_asset(
            con,
            document_id=derived_document_id,
            page_count=len(out_bites),
            pagination_scheme="chapter",
            provenance=(
                f"reformat generation {generation_id} of {source_document_id} "
                f"({recorded_provider or 'injected'}/{recorded_model})"
            ),
            license_basis=(
                f"derived from {source_document_id}; inherits its class "
                f"({source_content_class}) and holder (THREAD-CONTRACT §1.11a)"
            ),
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
        # Main's generation_records keeps the model (and the params blob).
        # Provider / DispatchCall event ids / cost and the §1.11a
        # rights_basis bind in the derived document's metadata above —
        # main's provenance schema carries no columns for them (Option C).
        ProvenanceStore().record_generation(
            con,
            record=GenerationRecordRow(
                generation_id=generation_id,
                owner_user_id=owner_user_id,
                source_document_id=source_document_id,
                derived_document_id=derived_document_id,
                prompt=prompt,
                model=recorded_model,
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
