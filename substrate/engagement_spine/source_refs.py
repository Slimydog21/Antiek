"""Knowledge-dense source references attached to deep-research spawns.

Residual after twin-promote (o): when spawning deep research, callers can
attach arXiv / Substack / generic URL references so investigation context
carries stable, citeable handles — without live HTTP. Ingest adapters
(``acquisition/substack``, arxiv OAI, sources ingest) remain the writers of
corpus documents; this module only **parses, normalizes, and attaches**
reference descriptors onto engagement-spine spawn rows.

Hard-to-vary rules:

* Pure parse/normalize — no network.
* Content-addressed ``ref_id`` so re-attach is idempotent.
* Does not open a second graph writer or call DuckDB.
* HTML-first listing of refs for human view (via project_to_html).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence
from urllib.parse import urlparse

from .store import EngagementStore

SourceKind = Literal["arxiv", "substack", "url", "unknown"]

# arXiv id: YYMM.NNNNN or older archive/YYMMNNN — modern form covers >99% of
# deep-research citations. Version suffix (vN) stripped for identity.
_ARXIV_ID_RE = re.compile(
    r"(?P<id>\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
_ARXIV_HOST_RE = re.compile(r"(?:^|\.)arxiv\.org$", re.IGNORECASE)
_SUBSTACK_HOST_RE = re.compile(r"(?:^|\.)substack\.com$", re.IGNORECASE)
_SUBSTACK_POST_RE = re.compile(r"/p/([A-Za-z0-9][A-Za-z0-9\-_]*)", re.IGNORECASE)


@dataclass(frozen=True)
class SourceReference:
    """A citeable external knowledge source handle (no body fetch)."""

    ref_id: str
    kind: SourceKind
    raw: str
    canonical_url: str | None = None
    external_id: str | None = None
    title_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "kind": self.kind,
            "raw": self.raw,
            "canonical_url": self.canonical_url,
            "external_id": self.external_id,
            "title_hint": self.title_hint,
        }


def _ref_id(kind: SourceKind, identity: str) -> str:
    digest = hashlib.sha256(f"{kind}:{identity}".encode("utf-8")).hexdigest()[:16]
    return f"sref_{digest}"


def extract_arxiv_id(raw: str) -> str | None:
    """Extract bare arXiv id from abs/pdf/html URL or bare id string."""
    text = (raw or "").strip()
    if not text:
        return None
    # Prefer path/id segments on arxiv hosts
    if "arxiv.org" in text.lower() or text[0].isdigit():
        m = _ARXIV_ID_RE.search(text)
        if m:
            return m.group("id")
    return None


def detect_source_kind(raw: str) -> SourceKind:
    """Classify a raw reference string without network I/O."""
    text = (raw or "").strip()
    if not text:
        return "unknown"
    lower = text.lower()
    # Explicit kind prefixes for operator/agent prompts
    if lower.startswith("arxiv:") or lower.startswith("arxiv/"):
        return "arxiv"
    if lower.startswith("substack:"):
        return "substack"

    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.hostname or "").lower()
    except Exception:
        parsed = None
        host = ""

    if host and _ARXIV_HOST_RE.search(host):
        return "arxiv"
    if extract_arxiv_id(text) and (
        host == "" or _ARXIV_HOST_RE.search(host) or text[0].isdigit()
    ):
        # Bare id like 2402.03300
        if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", text.strip(), re.I):
            return "arxiv"
        if host and _ARXIV_HOST_RE.search(host):
            return "arxiv"

    if host and _SUBSTACK_HOST_RE.search(host):
        return "substack"
    if parsed and _SUBSTACK_POST_RE.search(parsed.path or ""):
        # Custom-domain Substack posts commonly use /p/<slug>
        if "/p/" in (parsed.path or ""):
            return "substack"

    if text.startswith("http://") or text.startswith("https://") or "://" in text:
        return "url"
    if "." in text and " " not in text:
        return "url"
    return "unknown"


def parse_source_reference(
    raw: str,
    *,
    title_hint: str | None = None,
) -> SourceReference:
    """Parse one reference into a stable SourceReference (pure, offline)."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("reference raw text is required")

    # Strip optional kind prefix
    body = text
    lower = text.lower()
    if lower.startswith("arxiv:"):
        body = text.split(":", 1)[1].strip()
        kind: SourceKind = "arxiv"
    elif lower.startswith("arxiv/"):
        body = text.split("/", 1)[1].strip()
        kind = "arxiv"
    elif lower.startswith("substack:"):
        body = text.split(":", 1)[1].strip()
        kind = "substack"
    else:
        kind = detect_source_kind(text)

    canonical: str | None = None
    external_id: str | None = None

    if kind == "arxiv":
        aid = extract_arxiv_id(body) or extract_arxiv_id(text)
        if aid:
            external_id = aid
            canonical = f"https://arxiv.org/abs/{aid}"
            identity = f"arxiv:{aid}"
        else:
            identity = f"arxiv-raw:{body.lower()}"
            canonical = body if body.startswith("http") else None
    elif kind == "substack":
        try:
            parsed = urlparse(body if "://" in body else f"https://{body}")
            host = (parsed.hostname or "").lower()
            path = parsed.path or ""
        except Exception:
            host, path, parsed = "", "", None
        m = _SUBSTACK_POST_RE.search(path)
        slug = m.group(1) if m else None
        if host and slug:
            external_id = f"{host}/p/{slug}"
            canonical = f"https://{host}/p/{slug}"
            identity = f"substack:{external_id}"
        elif host:
            external_id = host.rstrip("/")
            canonical = f"https://{host}{path}" if path else f"https://{host}"
            identity = f"substack:{host}{path}"
        else:
            identity = f"substack-raw:{body.lower()}"
            canonical = body if body.startswith("http") else None
    elif kind == "url":
        url = body if "://" in body else f"https://{body}"
        canonical = url
        try:
            p = urlparse(url)
            identity = f"url:{(p.netloc + p.path).lower().rstrip('/')}"
            external_id = (p.netloc + p.path).rstrip("/")
        except Exception:
            identity = f"url:{url.lower()}"
            external_id = url
    else:
        identity = f"unknown:{body.lower()}"
        canonical = body if body.startswith("http") else None

    return SourceReference(
        ref_id=_ref_id(kind if kind != "unknown" else "unknown", identity),
        kind=kind,
        raw=text,
        canonical_url=canonical,
        external_id=external_id,
        title_hint=title_hint.strip() if title_hint and title_hint.strip() else None,
    )


def parse_source_references(
    raws: Sequence[str],
) -> list[SourceReference]:
    """Parse many references; de-dupe by ref_id (first wins)."""
    seen: set[str] = set()
    out: list[SourceReference] = []
    for raw in raws:
        if raw is None or not str(raw).strip():
            continue
        ref = parse_source_reference(str(raw))
        if ref.ref_id in seen:
            continue
        seen.add(ref.ref_id)
        out.append(ref)
    return out


def refs_from_rows(rows: Sequence[dict[str, Any]] | None) -> tuple[SourceReference, ...]:
    if not rows:
        return ()
    out: list[SourceReference] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            out.append(
                SourceReference(
                    ref_id=str(r["ref_id"]),
                    kind=r.get("kind", "unknown"),  # type: ignore[arg-type]
                    raw=str(r.get("raw") or ""),
                    canonical_url=r.get("canonical_url"),
                    external_id=r.get("external_id"),
                    title_hint=r.get("title_hint"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def merge_references(
    existing: Sequence[SourceReference],
    incoming: Sequence[SourceReference],
) -> tuple[SourceReference, ...]:
    """Idempotent union by ref_id; preserves existing order, appends new."""
    seen = {r.ref_id for r in existing}
    out = list(existing)
    for r in incoming:
        if r.ref_id in seen:
            continue
        seen.add(r.ref_id)
        out.append(r)
    return tuple(out)


def attach_source_references(
    spawn_id: str,
    references: Sequence[str | SourceReference],
    *,
    store: EngagementStore,
) -> tuple[Any, tuple[SourceReference, ...]]:
    """Attach parsed references onto an existing spawn row.

    Returns ``(ResearchSpawn, attached_refs_tuple)``. Re-attaching the same
    refs is a no-op (stable ref_ids). Raises KeyError if spawn missing.
    """
    # Local import avoids circular import at module load (spawn imports store only)
    from .spawn import ResearchSpawn, _from_row, _to_row

    row = store.get_spawn(spawn_id)
    if row is None:
        raise KeyError(f"unknown spawn_id: {spawn_id}")

    incoming: list[SourceReference] = []
    for item in references:
        if isinstance(item, SourceReference):
            incoming.append(item)
        else:
            if item is None or not str(item).strip():
                continue
            incoming.append(parse_source_reference(str(item)))

    prior = refs_from_rows(row.get("source_references"))
    merged = merge_references(prior, incoming)

    row = dict(row)
    row["source_references"] = [r.to_dict() for r in merged]
    store.put_spawn(row)
    spawn = _from_row(row)
    return spawn, merged


def list_source_references(spawn_id: str, *, store: EngagementStore) -> list[SourceReference]:
    row = store.get_spawn(spawn_id)
    if row is None:
        return []
    return list(refs_from_rows(row.get("source_references")))


def filter_references(
    refs: Sequence[SourceReference],
    *,
    kind: SourceKind | None = None,
    query: str | None = None,
) -> list[SourceReference]:
    """Search/filter attached refs for research context assembly."""
    q = (query or "").strip().lower()
    out: list[SourceReference] = []
    for r in refs:
        if kind is not None and r.kind != kind:
            continue
        if q:
            hay = " ".join(
                x
                for x in (
                    r.raw,
                    r.canonical_url or "",
                    r.external_id or "",
                    r.title_hint or "",
                    r.kind,
                )
            ).lower()
            if q not in hay:
                continue
        out.append(r)
    return out


def source_references_html(
    refs: Sequence[SourceReference],
    *,
    document_id: str = "spawn-source-refs",
    title: str = "Deep-research source references",
) -> str:
    """HTML-first human view of attached references (never PDF)."""
    from .project import project_to_html

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": title}],
        }
    ]
    if not refs:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no source references attached)"}],
            }
        )
    for r in refs:
        label = f"[{r.kind}] {r.canonical_url or r.raw}"
        if r.external_id:
            label = f"[{r.kind}] {r.external_id} — {r.canonical_url or r.raw}"
        blocks.append(
            {
                "type": "paragraph",
                "attrs": {"data-ref-id": r.ref_id, "data-kind": r.kind},
                "content": [{"type": "text", "text": label}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=document_id,
        creator="source_refs",
    )


def spawn_from_highlight_with_references(
    selection: Any,
    *,
    store: EngagementStore,
    references: Sequence[str | SourceReference] = (),
    model_id: str | None = None,
    force_new: bool = False,
    research_tier: str | None = None,
) -> Any:
    """Product entry: reserve spawn from highlight, then attach source refs.

    Composes ``spawn_from_highlight`` + ``attach_source_references``. No network.
    Residual (ji): optional ``research_tier`` passed through to spawn reservation.
    """
    from .spawn import spawn_from_highlight

    spawn = spawn_from_highlight(
        selection,
        store=store,
        model_id=model_id,
        force_new=force_new,
        research_tier=research_tier,
    )
    if not references:
        return spawn
    spawn, _merged = attach_source_references(spawn.spawn_id, references, store=store)
    return spawn
