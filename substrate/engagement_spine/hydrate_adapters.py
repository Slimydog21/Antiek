"""Publication body adapters for hydrate_reference (residual bi).

Wires knowledge-dense publication fetchers into the hydrate product path
without coupling hydrate.py to httpx/arXiv throttle. Live network is
**opt-in** via injectable clients or ``use_live=True`` (tests always inject).

Default offline path remains identity-only (hydrate.py).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .source_refs import SourceReference, extract_arxiv_id

# (SourceReference) -> dict title/body_text/abstract/canonical_url
FetchPublication = Callable[[SourceReference], dict[str, Any]]


def arxiv_metadata_fetch_publication(
    *,
    fetch_by_id: Callable[[str], Any] | None = None,
) -> FetchPublication:
    """Build a fetch_publication callable that lands arXiv abstracts as body.

    When ``fetch_by_id`` is None and the call is for an arxiv ref, raises
    so callers must inject a client (honest no silent network).
    """

    def _fetch(ref: SourceReference) -> dict[str, Any]:
        if ref.kind != "arxiv":
            return {}
        arxiv_id = ref.external_id or extract_arxiv_id(ref.raw) or ""
        arxiv_id = str(arxiv_id).strip()
        if not arxiv_id:
            return {}
        if fetch_by_id is None:
            raise RuntimeError(
                "arxiv fetch_by_id not injected — refuse silent live network"
            )
        paper = fetch_by_id(arxiv_id)
        # Support dataclass ArxivPaper or plain dict
        if hasattr(paper, "title"):
            title = str(paper.title or "")
            abstract = str(paper.abstract or "")
            abs_url = str(paper.abs_url or "") or None
            authors = list(paper.authors or [])
        elif isinstance(paper, dict):
            title = str(paper.get("title") or "")
            abstract = str(paper.get("abstract") or "")
            abs_url = paper.get("abs_url") or paper.get("canonical_url")
            authors = list(paper.get("authors") or [])
        else:
            raise TypeError("fetch_by_id must return ArxivPaper or dict")

        body = abstract.strip()
        if authors:
            body = f"Authors: {', '.join(authors)}\n\n{body}".strip()
        return {
            "title": title.strip() or f"arXiv:{arxiv_id}",
            "body_text": body,
            "abstract": abstract.strip(),
            "canonical_url": abs_url or f"https://arxiv.org/abs/{arxiv_id}",
            "source": "acquisition.arxiv",
        }

    return _fetch


def substack_post_fetch_publication(
    *,
    fetch_post: Callable[[str], Any] | None = None,
) -> FetchPublication:
    """Build fetch_publication for substack refs via injectable post fetcher.

    ``fetch_post`` receives canonical/raw URL and returns a Post-like object
    or dict with title/body_markdown/body_html/post_url. Refuses silent network
    when ``fetch_post`` is None and kind is substack.
    """

    def _fetch(ref: SourceReference) -> dict[str, Any]:
        if ref.kind != "substack":
            return {}
        url = ref.canonical_url or ref.raw
        if not url:
            return {}
        if fetch_post is None:
            raise RuntimeError(
                "substack fetch_post not injected — refuse silent live network"
            )
        post = fetch_post(str(url))
        if hasattr(post, "title"):
            title = str(post.title or "")
            body = str(
                post.body_markdown
                or post.body_html
                or ""
            )
            post_url = getattr(post, "post_url", None) or url
            author = str(post.author or "")
            truncated = bool(getattr(post, "truncated", False))
        elif isinstance(post, dict):
            title = str(post.get("title") or "")
            body = str(
                post.get("body_markdown")
                or post.get("body_html")
                or post.get("body_text")
                or ""
            )
            post_url = post.get("post_url") or post.get("canonical_url") or url
            author = str(post.get("author") or "")
            truncated = bool(post.get("truncated", False))
        else:
            raise TypeError("fetch_post must return Post-like or dict")

        if author:
            body = f"Author: {author}\n\n{body}".strip()
        notes_extra = " (truncated/paywall teaser)" if truncated else ""
        return {
            "title": (title.strip() or "Substack post") + notes_extra,
            "body_text": body.strip(),
            "canonical_url": str(post_url),
            "source": "acquisition.substack",
            "truncated": truncated,
        }

    return _fetch


def compose_fetch_publication(
    *adapters: FetchPublication,
) -> FetchPublication:
    """Try adapters in order; first non-empty dict wins."""

    def _composed(ref: SourceReference) -> dict[str, Any]:
        for adapter in adapters:
            try:
                out = adapter(ref) or {}
            except Exception:
                continue
            if out:
                return out
        return {}

    return _composed


def hydrate_with_arxiv_adapter(
    raw: str,
    *,
    store: Any,
    fetch_by_id: Callable[[str], Any] | None = None,
    include_html: bool = True,
    attach_spawn_id: str | None = None,
) -> Any:
    """Product entry: hydrate using arXiv metadata adapter when applicable.

    For non-arxiv refs, falls back to identity-only hydrate (no body).
    """
    from .hydrate import hydrate_reference

    adapters: list[FetchPublication] = []
    if fetch_by_id is not None:
        adapters.append(arxiv_metadata_fetch_publication(fetch_by_id=fetch_by_id))
    fetch = compose_fetch_publication(*adapters) if adapters else None
    return hydrate_reference(
        raw,
        store=store,
        fetch_publication=fetch,
        include_html=include_html,
        attach_spawn_id=attach_spawn_id,
    )


def hydrate_with_publication_adapters(
    raw: str,
    *,
    store: Any,
    arxiv_fetch_by_id: Callable[[str], Any] | None = None,
    substack_fetch_post: Callable[[str], Any] | None = None,
    include_html: bool = True,
    attach_spawn_id: str | None = None,
) -> Any:
    """Product entry: hydrate with arXiv and/or Substack injectable adapters."""
    from .hydrate import hydrate_reference

    adapters: list[FetchPublication] = []
    if arxiv_fetch_by_id is not None:
        adapters.append(
            arxiv_metadata_fetch_publication(fetch_by_id=arxiv_fetch_by_id)
        )
    if substack_fetch_post is not None:
        adapters.append(
            substack_post_fetch_publication(fetch_post=substack_fetch_post)
        )
    fetch = compose_fetch_publication(*adapters) if adapters else None
    return hydrate_reference(
        raw,
        store=store,
        fetch_publication=fetch,
        include_html=include_html,
        attach_spawn_id=attach_spawn_id,
    )
