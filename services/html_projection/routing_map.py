"""SPR-06 M4: routing map + emission dispatch.

The SINGLE source of format-choice: each share surface name -> its ordered
allowed formats. A NEW format or a surface's format set changes HERE and
NOWHERE else — that is the whole point of this module (the defensibility
artifact: one place answers "which surface emits which format and why").

``emit`` dispatches on ``fmt`` but the SET of formats per surface is only in
``SURFACE_FORMATS``.  The routing map is the ONLY place a format-choice
conditional lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

from services.antiek_format.native_writer import WriterInput, write_antiek
from services.antiek_format.signature import Keypair
from services.antiek_format.single_file import build_single_file
from services.html_projection.context import RenderContext
from services.html_projection.renderer import render


# ── Closed format set ──

_FIXED_CREATED_AT: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
"""Fixed timestamp for deterministic ``.antiek`` container emission.

The writer falls back to ``datetime.now()`` when ``created_at`` is
``None``; passing a fixed value ensures byte-identical output for
the same inputs.  Callers that have a stored substrate timestamp
should supply it directly via ``WriterInput.created_at``; this
constant is the routing-map's deterministic default."""

EXPORT_FORMATS: tuple[str, ...] = ("html", "antiek", "antiek_html")
"""The canonical closed set of export formats.  Add a new format here
and in ``SURFACE_FORMATS`` — nowhere else."""


# ── The single source of truth: surface -> allowed formats ──

SURFACE_FORMATS: dict[str, tuple[str, ...]] = {
    "notebook_share": ("html", "antiek", "antiek_html"),
    "synthesis_share": ("html", "antiek", "antiek_html"),
    "theme_share": ("html", "antiek"),
}
"""Each share surface name -> its ordered allowed formats.

A NEW format or a surface's format set changes HERE and NOWHERE else.
``formats_for`` reads this; ``emit`` dispatches on the format string;
but the SET of legal formats per surface is only in this dict.

Unknown surfaces default to ``("html",)`` via ``formats_for``."""


def formats_for(surface: str) -> tuple[str, ...]:
    """The allowed formats for a surface.

    Returns the entry from ``SURFACE_FORMATS`` if present;
    ``("html",)`` for an unknown surface (the safe default —
    plain HTML requires no signing and is universally readable).
    """
    return SURFACE_FORMATS.get(surface, ("html",))


# ── Export item ──


@dataclass(frozen=True)
class ExportItem:
    """Canonical content + provenance for emission.

    Carries exactly what ``emit`` needs to produce any of the three
    artifact formats.  Frozen so two calls with the same item are
    guaranteed identical inputs.
    """

    content_tiptap: dict
    title: Optional[str]
    document_id: str
    user_id: str
    notebook_id: str
    parent_document_id: Optional[str] = None
    content_class: str = "notebook"


# ── Emission dispatch ──


def emit(
    item: ExportItem,
    fmt: str,
    *,
    keypair: Optional[Keypair] = None,
) -> Union[bytes, str]:
    """Emit an export item in the requested format.

    Parameters
    ----------
    item : ExportItem
        Canonical content + provenance.
    fmt : str
        One of ``EXPORT_FORMATS``.
    keypair : Keypair, optional
        Required for ``"antiek"`` and ``"antiek_html"`` formats.

    Returns
    -------
    bytes or str
        ``"html"`` -> str, ``"antiek"`` -> bytes, ``"antiek_html"`` -> str.

    Raises
    ------
    ValueError
        If ``fmt`` is unknown, or if ``fmt`` requires a keypair and
        none was supplied.
    """
    if fmt not in EXPORT_FORMATS:
        raise ValueError(
            f"emit: unknown format {fmt!r}; valid: {sorted(EXPORT_FORMATS)}"
        )

    # Shared doc-model for the renderer.  The routing map carries zero
    # edges — edges arrive from the caller's own data, not from the
    # format dispatch.
    doc_model = {
        "content": item.content_tiptap.get("content", []),
        "title": item.title,
        "edges": [],
    }

    if fmt == "html":
        return render(doc_model, RenderContext())

    # Signed formats require a keypair.
    if keypair is None:
        raise ValueError(
            f"emit: format {fmt!r} requires a keypair"
        )

    if fmt == "antiek":
        inp = WriterInput(
            notebook_id=item.notebook_id,
            user_id=item.user_id,
            document_id=item.document_id,
            parent_document_id=item.parent_document_id,
            content_class=item.content_class,
            title=item.title,
            content_tiptap=item.content_tiptap,
            created_at=_FIXED_CREATED_AT,
        )
        return write_antiek(inp, keypair=keypair)

    # fmt == "antiek_html"
    projection = render(doc_model, RenderContext())
    return build_single_file(projection, keypair=keypair)
