"""Personal document space — collect / categorize / match the reader's OWN
created deliverables (Read SPR-13).

This is the "personal bed of information that labels itself": the reader's
CREATED assets (the SPR-08 meta-reading deliverables) plus the reads they
saved (the SPR-07 ``source.read`` history) — distinct from the raw library of
source books (SPR-07 owns that). It does three things, all as thin SELECTORS
over the one graph — NO new store:

  • ``list_personal_assets`` — enumerate the created deliverables + saved reads
    from the EVENT LOG (the same cross-investigation scan ``list_investigations``
    and the §7 daemon use). Substrate-backed; no second document store.
  • ``categorize_assets`` — cluster the deliverables into SYSTEM-named
    categories from their embeddings (reuse ``SentenceTransformerEmbedding`` —
    NO new embedder). Deterministic on a fixture; honest recency/uncategorized
    fallback below a stated stability bound (rigor #1). The system names the
    categories; the user never hand-organizes folders.
  • ``match_document_to_investigations`` — given a doc, rank the candidate
    research projects (reconstructed from ``investigation.start_requested``
    events) by semantic similarity of the doc to each project's QUESTION, so the
    surface can SUGGEST filing it into the related project. Suggest-only — the
    accept path (the filing typed event) lives in the API + frontend; this
    selector never files anything.

§9.0: clustering + matching reuse ``substrate.graph.search``'s embedding model;
the default ``policy_tag='attribution_eligible'`` keeps restricted content out
of any retrieval. Asset prose embedded here is the reader's OWN deliverable
(model-synthesized over already-gated owned chunks at generation time), not a
withheld source body — so embedding it leaks nothing the SPR-08 gate didn't
already pass.

WHY EVENT-LOG SCAN, NOT A TABLE: meta-reading assets are typed events
(``read.meta_reading.generated`` under the ``read-meta-{asset_id}``
investigation id) and saved reads are ``source.read`` events (under the
``read-{document_id}`` reading thread). Neither is a DuckDB table — they live
on the append-only log, the substrate's source of truth. Reconstructing from
the log is the SAME posture ``list_investigations`` (app.py) takes for
investigations, which also are not a table.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from substrate.event_log.events import default_events_dir, trajectory
from substrate.graph.search import EmbeddingModel

# ---------------------------------------------------------------------------
# Event-log enumeration helpers (mirror the daemon / list_investigations scan)
# ---------------------------------------------------------------------------


def _list_investigation_ids(events_dir: str) -> list[str]:
    """Enumerate investigation ids by scanning the events dir for jsonl +
    parquet files. Mirrors ``orchestration.continuous.daemon._list_investigation_ids``
    and ``event_log.events.action_counts`` — the one sanctioned way to discover
    every trajectory without an investigations table."""
    if not os.path.isdir(events_dir):
        return []
    seen: set[str] = set()
    for fn in os.listdir(events_dir):
        if fn.endswith(".parquet"):
            seen.add(fn[: -len(".parquet")])
        elif fn.endswith(".jsonl"):
            seen.add(fn[: -len(".jsonl")])
    return sorted(seen)


# ---------------------------------------------------------------------------
# M1 — list the personal-space assets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonalAsset:
    """One item in the personal space — a created deliverable or a saved read.

    ``kind`` distinguishes the two so the surface can render the created-asset
    vs source-book distinction (M4) and the meta-docs tab filters on it.
    ``open_route`` is the in-app path the surface routes to so the item opens
    back into the SPR-07 reader / SPR-08 meta-doc view (M1 acceptance)."""

    asset_id: str
    kind: str  # "meta_reading" | "saved_read"
    title: str
    # The reader's prompt (meta_reading) or null (saved_read).
    prompt: str | None
    # The owned doc(s) the asset is about — meta_reading's corpus, or the single
    # read document for a saved_read. The §9 provenance anchor.
    document_ids: list[str]
    emitted_at: str | None
    open_route: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "title": self.title,
            "prompt": self.prompt,
            "document_ids": self.document_ids,
            "emitted_at": self.emitted_at,
            "open_route": self.open_route,
        }


def _title_for_meta_reading(payload: dict[str, Any]) -> str:
    """A human title for a meta-reading asset — its prompt, bounded; never the
    asset_id (which is an opaque handle). Honest fallback when promptless."""
    prompt = (payload.get("prompt") or "").strip()
    if prompt:
        return prompt if len(prompt) <= 120 else prompt[:117] + "…"
    return "Untitled reading"


def list_personal_assets(
    *,
    events_dir: str | None = None,
    include_saved_reads: bool = True,
    book_title_resolver: Any | None = None,
) -> list[PersonalAsset]:
    """Enumerate the personal-space assets from the event log, newest first.

    Created deliverables come from ``read.meta_reading.generated`` events (one
    per saved meta-reading). Saved reads come from ``source.read`` events
    (the SPR-07 reading history) — deduped per document, keyed to the most
    recent read of that document. ``book_title_resolver`` (optional) maps a
    document_id → a title so a saved read shows the book's name rather than its
    id; when absent the id is used (honest, never fabricated).

    CURATED, not a raw dump (M1): only the reader's CREATED assets + reads they
    actually dwelled on long enough to count as read (the SPR-07 dwell gate
    already filtered ``source.read`` to genuine reads) — never every document in
    the substrate (that is the operator DocumentsIndex's job).
    """
    resolved = events_dir or default_events_dir()
    assets: list[PersonalAsset] = []
    # Saved reads dedupe to the latest read of each document.
    saved_latest: dict[str, dict[str, Any]] = {}

    for iid in _list_investigation_ids(resolved):
        for ev in trajectory(iid, events_dir=resolved):
            at = ev.get("action_type")
            payload = ev.get("payload") or {}
            if at == "read.meta_reading.generated":
                asset_id = payload.get("asset_id") or iid
                corpus = list(payload.get("corpus_document_ids") or [])
                assets.append(
                    PersonalAsset(
                        asset_id=asset_id,
                        kind="meta_reading",
                        title=_title_for_meta_reading(payload),
                        prompt=(payload.get("prompt") or None),
                        document_ids=corpus,
                        emitted_at=ev.get("emitted_at"),
                        # The saved asset re-opens in the meta-doc view by id.
                        open_route=f"/read/meta-reading/{asset_id}",
                    )
                )
            elif include_saved_reads and at == "source.read":
                doc_id = ev.get("document_id")
                if not doc_id:
                    continue
                prev = saved_latest.get(doc_id)
                emitted = ev.get("emitted_at") or ""
                if prev is None or emitted > (prev.get("emitted_at") or ""):
                    saved_latest[doc_id] = {"emitted_at": emitted}

    for doc_id, info in saved_latest.items():
        title = doc_id
        if book_title_resolver is not None:
            try:
                resolved_title = book_title_resolver(doc_id)
                if resolved_title:
                    title = resolved_title
            except Exception:  # pragma: no cover — resolver is best-effort
                pass
        assets.append(
            PersonalAsset(
                asset_id=f"read:{doc_id}",
                kind="saved_read",
                title=title,
                prompt=None,
                document_ids=[doc_id],
                emitted_at=info.get("emitted_at") or None,
                # A saved read re-opens in the SPR-07 in-book reader.
                open_route=f"/read/{doc_id}",
            )
        )

    # Newest first (ISO8601 sorts lexically); a missing timestamp sinks.
    assets.sort(key=lambda a: a.emitted_at or "", reverse=True)
    return assets


# ---------------------------------------------------------------------------
# M2 — auto-categorization (system labels via deterministic clustering)
# ---------------------------------------------------------------------------

# Below this many assets, clustering on embeddings is genuinely unstable — a
# 2-asset "cluster" is as likely coincidence as theme, and the salient-term
# label flips run-to-run on tiny corpora. So below the bound we DON'T fabricate
# clean labels: we ship the honest "recency" fallback (one bucket, newest
# first). See docs/decisions/spr-13-personal-space-and-filing.md (rigor #1).
MIN_ASSETS_FOR_CLUSTERING: int = 4

# Two assets join the same category iff their cosine similarity is at or above
# this. Connected-components over that threshold graph gives the clusters. The
# number is justified in the decision doc + the M3 threshold comment; 0.55 is
# deliberately conservative — it groups genuinely-related deliverables (same
# subject treated across reads) without merging the whole space into one bucket.
CLUSTER_SIMILARITY_THRESHOLD: float = 0.55

# Stopwords for naming a cluster from its salient terms — mirrors the frontend
# documentsByTheme STOPWORDS idiom (the term-extraction pattern the spec points
# to), kept in sync deliberately so a category name reads like a theme, not
# scaffolding.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "how", "what", "why", "when", "where", "who", "which", "whom", "whose",
    "this", "that", "these", "those", "it", "its", "as", "at", "by", "from",
    "into", "about", "over", "under", "between", "vs", "versus", "can", "could",
    "should", "would", "will", "may", "might", "than", "then", "so", "if",
    "my", "your", "their", "his", "her", "our", "me", "you", "they",
})


@dataclass(frozen=True)
class AssetCategory:
    """One system-named category and the assets in it. ``ordering`` is "theme"
    when clusters emerged from embeddings, "recency" when the corpus was below
    the stability bound and we fell back honestly (M2 fallback).

    ``category_id`` is the STABLE, UNIQUE identity the surface keys on — two
    distinct clusters can legitimately share a salient-term ``label`` (same
    vocabulary, different embeddings), so the human-readable label is NOT a safe
    UI key; the id is. For a theme cluster it is the cluster's lowest asset_id
    (disjoint clusters ⇒ unique); for the recency bucket it is ``"recency"``."""

    category_id: str
    label: str
    asset_ids: list[str]
    ordering: str  # "theme" | "recency"


@dataclass(frozen=True)
class CategorizedSpace:
    categories: list[AssetCategory]
    ordering: str  # "theme" | "recency" — the whole-space verdict
    # The doc-count bound below which we fell back, surfaced so the UI can SAY
    # it ("organizing kicks in at N assets") rather than pretend.
    stability_bound: int = field(default=MIN_ASSETS_FOR_CLUSTERING)


def _salient_terms(texts: Sequence[str], *, top_k: int = 3) -> list[str]:
    """The most frequent content words across a cluster's texts — the label.
    Mirrors documentsByTheme.themeTermsFromInvestigations: lowercase, split on
    non-alphanumerics, drop stopwords + sub-3-char tokens, rank by frequency.
    Deterministic: ties break alphabetically so the same cluster names the same
    way run-to-run (the determinism the fixture asserts)."""
    counts: dict[str, int] = {}
    for t in texts:
        for raw in t.lower().replace("\n", " ").split():
            w = "".join(ch for ch in raw if ch.isalnum())
            if len(w) < 3 or w in _STOPWORDS:
                continue
            counts[w] = counts.get(w, 0) + 1
    if not counts:
        return []
    # Most-frequent first; alphabetical tiebreak → stable, not insertion-order.
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_k]]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def categorize_assets(
    assets: Sequence[PersonalAsset],
    *,
    model: EmbeddingModel,
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
    min_for_clustering: int = MIN_ASSETS_FOR_CLUSTERING,
) -> CategorizedSpace:
    """Cluster the personal-space assets into SYSTEM-named categories.

    DETERMINISTIC by construction (so the fixture test is non-flaky):
      • assets are processed in a STABLE order (sorted by asset_id), so
        connected-components labels are assigned in a reproducible order;
      • the similarity graph is symmetric + threshold-based — same embeddings
        ⇒ same edges ⇒ same components;
      • each cluster's name is its salient terms with an alphabetical tiebreak.

    HONEST FALLBACK (rigor #1): below ``min_for_clustering`` assets, OR when the
    embedding model can't be loaded, we return ONE "Recently read & created"
    bucket in recency order rather than fabricate theme labels a tiny/embedding-
    less corpus can't reliably support. The verdict rides on ``ordering`` so the
    surface SAYS which mode is active.
    """
    items = list(assets)
    if len(items) < min_for_clustering:
        return CategorizedSpace(
            categories=[
                AssetCategory(
                    category_id="recency",
                    label="Recently read & created",
                    asset_ids=[a.asset_id for a in items],
                    ordering="recency",
                )
            ]
            if items
            else [],
            ordering="recency",
            stability_bound=min_for_clustering,
        )

    # Stable node ordering — the determinism keystone.
    items.sort(key=lambda a: a.asset_id)

    # Embed each asset's text (prompt + title for a meta_reading; title for a
    # saved_read). Embedding-text is the reader's own deliverable, never a
    # source body (§9.0 noted in the module docstring).
    def _asset_text(a: PersonalAsset) -> str:
        return " ".join(p for p in (a.prompt, a.title) if p)

    try:
        vectors = [list(model.encode(_asset_text(a))) for a in items]
    except Exception:  # pragma: no cover — model unavailable → honest fallback
        return CategorizedSpace(
            categories=[
                AssetCategory(
                    category_id="recency",
                    label="Recently read & created",
                    asset_ids=[a.asset_id for a in items],
                    ordering="recency",
                )
            ],
            ordering="recency",
            stability_bound=min_for_clustering,
        )

    n = len(items)
    # Connected components over the threshold similarity graph (union-find).
    parent = list(range(n))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x: int, y: int) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            # Lower root wins → deterministic component representative.
            parent[max(rx, ry)] = min(rx, ry)

    for i in range(n):
        for j in range(i + 1, n):
            if _cosine(vectors[i], vectors[j]) >= threshold:
                _union(i, j)

    # Group by component root, preserving the stable item order within each.
    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(_find(i), []).append(i)

    # Name each component from its salient terms, with a STABLE UNIQUE
    # ``category_id`` (the cluster's lowest asset_id — disjoint clusters ⇒
    # unique). Two distinct clusters CAN share top salient terms (same
    # vocabulary, different embeddings split them); when that happens the LABEL
    # is disambiguated — first by pulling in the next distinguishing term, then
    # by an ordinal — so no two categories ever carry the same label. (A
    # duplicate label would otherwise collide as a UI list key and silently drop
    # a section; the id is the safe key, the label is for humans.)
    categories: list[AssetCategory] = []
    seen_labels: set[str] = set()
    for root in sorted(comps):  # deterministic component ordering
        idxs = comps[root]
        # Pull a few extra terms (top 6) so a label collision can be broken by a
        # real distinguishing term before we fall back to an ordinal.
        terms = _salient_terms([_asset_text(items[k]) for k in idxs], top_k=6)
        # System-named: the top salient terms joined; honest "Uncategorized" when
        # a cluster has no extractable content word (rigor #1: never a fake label).
        label = " · ".join(terms[:3]) if terms else "Uncategorized"
        # Disambiguate a collision with the next distinguishing term(s)…
        extra = 4
        while label in seen_labels and extra <= len(terms):
            label = " · ".join(terms[:extra])
            extra += 1
        # …then, only if the clusters are genuinely term-identical, an ordinal.
        if label in seen_labels:
            n = 2
            while f"{label} ({n})" in seen_labels:
                n += 1
            label = f"{label} ({n})"
        seen_labels.add(label)
        categories.append(
            AssetCategory(
                category_id=f"cat:{items[idxs[0]].asset_id}",
                label=label,
                asset_ids=[items[k].asset_id for k in idxs],
                ordering="theme",
            )
        )

    return CategorizedSpace(
        categories=categories,
        ordering="theme",
        stability_bound=min_for_clustering,
    )


# ---------------------------------------------------------------------------
# M3 — match a document to candidate research projects (suggest filing)
# ---------------------------------------------------------------------------

# A document is only SUGGESTED for filing into a project when its similarity to
# that project's question is at or above this. 0.45 is the justified cutoff:
# below it the doc and the question share no real subject (cross-domain pairs
# embed under ~0.4 with MiniLM), so a suggestion there would be noise the reader
# learns to dismiss; at/above it they're discussing the same thing. It sits
# BELOW the 0.55 clustering threshold deliberately — filing into an existing,
# user-named project is a lower bar to CLEAR than auto-grouping two of the
# reader's own deliverables (a clustering mistake silently mis-files; a filing
# suggestion is only ever offered, the reader accepts or declines). The full
# justification + reconsider-if is in docs/decisions/spr-13-personal-space-and-filing.md.
MATCH_SUGGESTION_THRESHOLD: float = 0.45


@dataclass(frozen=True)
class ProjectMatch:
    investigation_id: str
    question: str
    score: float


def _list_candidate_projects(events_dir: str) -> list[tuple[str, str]]:
    """Reconstruct candidate research projects (investigation_id, question)
    from ``investigation.start_requested`` events on the log.

    Investigations are NOT a table (schema.py defers them); the question lives
    on the start-requested payload's ``question`` field (events.py
    InvestigationStartRequestedPayload + app.py list_investigations reads it the
    same way). A cascade leaf carries ``sub_question`` instead — included too so
    a doc can be filed into a fan-out child. Projects with no usable question
    are skipped (nothing to match against — honest, not a 0-score candidate)."""
    out: list[tuple[str, str]] = []
    for iid in _list_investigation_ids(events_dir):
        question: str | None = None
        for ev in trajectory(iid, events_dir=events_dir):
            if ev.get("action_type") != "investigation.start_requested":
                continue
            payload = ev.get("payload") or {}
            q = payload.get("question") or payload.get("sub_question")
            if q and q.strip():
                question = q.strip()
                break
        if question:
            out.append((iid, question))
    return out


def match_document_to_investigations(
    *,
    doc_text: str,
    model: EmbeddingModel,
    events_dir: str | None = None,
    threshold: float = MATCH_SUGGESTION_THRESHOLD,
    top_k: int = 3,
    exclude_investigation_id: str | None = None,
) -> list[ProjectMatch]:
    """Rank candidate research projects by how well ``doc_text`` matches each
    project's question. Returns the matches AT OR ABOVE ``threshold``, best
    first, capped at ``top_k`` — so the surface can name the top match (or,
    per rigor #3, surface >1 candidate when a doc matches several projects)
    WITHOUT double-filing or auto-shipping to all of them.

    SUGGEST-ONLY: this selector ranks; it never files. The accept path (the
    ``document.filed_into_investigation`` typed event) is the only mutator and
    it fires only on explicit user accept (the frontend + API). An empty list
    means "no project is a good enough match" — the surface shows no suggestion
    rather than a hollow one.

    ``exclude_investigation_id`` drops a project the doc is already filed into
    (no point suggesting its current home). Reuses the SAME embedding model
    SPR-04 curate + §7 search use — no new matcher.
    """
    if not doc_text.strip():
        return []
    resolved = events_dir or default_events_dir()
    candidates = _list_candidate_projects(resolved)
    if not candidates:
        return []

    try:
        doc_vec = list(model.encode(doc_text))
    except Exception:  # pragma: no cover — model unavailable → no suggestion
        return []

    matches: list[ProjectMatch] = []
    for iid, question in candidates:
        if exclude_investigation_id is not None and iid == exclude_investigation_id:
            continue
        try:
            q_vec = list(model.encode(question))
        except Exception:  # pragma: no cover
            continue
        score = _cosine(doc_vec, q_vec)
        if score >= threshold:
            matches.append(ProjectMatch(iid, question, round(score, 4)))

    # Best first; investigation_id tiebreak keeps a tie deterministic (rigor #3:
    # a doc matching MULTIPLE projects ranks them, never double-files).
    matches.sort(key=lambda m: (-m.score, m.investigation_id))
    return matches[:top_k]
