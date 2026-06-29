"""The single routing map for share-surface → artifact-format emission (SPR-06 M4).

THE ONE PLACE that answers "which share surface emits which artifact format, and
why." That question — the defensibility artifact this sprint ships — has a single
home: the ``SURFACE_FORMATS`` table. A surface's format set, or a brand-new
format, changes in that table and NOWHERE ELSE.

``emit`` is the emission dispatch: the reusable capability the share routes call.
It fans an ``ExportItem`` out to the right EXISTING writer — ``render`` (the
SPR-02 HTML projection), ``write_antiek`` (the signed container), or
``build_single_file`` (the signed single-file HTML). It reuses those writers
verbatim; it does NOT reimplement container writing, signing, or rendering.

Why ``emit`` never consults ``SURFACE_FORMATS``
-----------------------------------------------
The surface/format *policy* and the format/writer *dispatch* are deliberately
split so the routing map stays a single decision point:

- ``SURFACE_FORMATS`` + ``formats_for`` answer "is this format allowed for this
  surface?" — that is the policy. A route calls ``formats_for(surface)`` and then
  ``emit`` only a format the table permits.
- ``emit`` answers "given a format, which writer produces the artifact?" — that
  is pure mechanical dispatch.

If ``emit`` consulted the table, the format-choice conditional would live in two
places and the single-decision-point invariant would break. So ``emit`` dispatches
on ``fmt`` alone and treats the surface as out of scope. The hard rule — "the
routing map is the ONLY place a format-choice conditional lives, and the SET of
formats per surface is only in ``SURFACE_FORMATS``" — is satisfied by keeping the
set in the table and keeping ``emit`` set-agnostic.

Determinism / parity
--------------------
``emit`` of the same ``(item, fmt, keypair)`` is byte-identical across calls —
this is the parity the spec demands: two routes calling ``emit`` with the same
input get identical artifacts because emission is deterministic. The writers
already guarantee determinism (the renderer carries no wall-clock; the container
writer pins zip timestamps and uses canonical JSON; Ed25519 signing is
deterministic). The one wall-clock ``emit`` could introduce is the container
manifest's ``created_at`` — that field is part of the signed bytes, so a
``now()`` there would make two ``emit`` calls of the same item differ. We pin it
to a fixed constant (``_FIXED_CREATED_AT``) instead. The ``ExportItem`` shape this
sprint fixes carries no ``created_at``, so a route cannot supply a stored
timestamp through it; the constant is the parity-preserving choice.
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

EXPORT_FORMATS: tuple[str, ...] = ("html", "antiek", "antiek_html")
"""The closed set of artifact formats any share surface can emit. A new format
joins this tuple AND the relevant ``SURFACE_FORMATS`` rows — both here, nowhere
else."""

SURFACE_FORMATS: dict[str, tuple[str, ...]] = {
    "notebook_share": EXPORT_FORMATS,
    "synthesis_share": EXPORT_FORMATS,
    "theme_share": ("html", "antiek"),
}
"""THE SINGLE source of format-choice. Each share surface name maps to its
ordered allowed formats. This is the defensibility artifact: one place answers
"which surface emits which format and why." A surface's format set changes here
and nowhere else."""

_DEFAULT_FORMATS: tuple[str, ...] = ("html",)
"""The fallback for an unknown surface. HTML is the lowest-trust format — an
unsigned projection — so an unrecognized surface never silently earns a signed
artifact (container or single-file). A new surface gets a real row in
``SURFACE_FORMATS``; this closed default keeps unknown surfaces honest."""

_FIXED_CREATED_AT: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
"""The first-save timestamp stamped into every emitted container's manifest. It
is part of the signed bytes, so it MUST be a constant (not wall-clock) for
``emit`` to be byte-identical across calls — see the module docstring's parity
section. The route that wraps ``emit`` owns the real stored timestamp; this
constant is the emission-layer pin that makes parity hold."""


@dataclass(frozen=True)
class ExportItem:
    """The canonical content + provenance one share surface exports.

    Carries exactly what the three writers need and nothing the master-spec
    invariant forbids: the TipTap doc (source of truth) + manifest provenance.
    Frozen so an item handed to ``emit`` cannot be mutated mid-dispatch — two
    routes holding the same item get identical artifacts. There is no
    ``created_at`` field: the emission layer pins that to a constant for parity
    (see ``_FIXED_CREATED_AT``), and no substrate-derived field is carried — a
    ``.antiek`` carries canonical text + user-asserted provenance only.
    """

    content_tiptap: dict
    title: Optional[str]
    document_id: str
    user_id: str
    notebook_id: str
    parent_document_id: Optional[str] = None
    content_class: str = "notebook"


def formats_for(surface: str) -> tuple[str, ...]:
    """The ordered formats a share surface may emit.

    Unknown surface → ``("html",)``: the safe, unsigned default. ``formats_for``
    is a pure lookup over ``SURFACE_FORMATS`` — no conditional beyond "is the
    surface in the table", which is the single decision point this module owns.
    """
    return SURFACE_FORMATS.get(surface, _DEFAULT_FORMATS)


def emit(
    item: ExportItem, fmt: str, *, keypair: Optional[Keypair] = None
) -> Union[bytes, str]:
    """Emit one artifact from ``item`` in the requested format.

    Pure mechanical dispatch on ``fmt`` — it does NOT consult
    ``SURFACE_FORMATS`` (see the module docstring for why that split keeps the
    routing map a single decision point). The route resolves surface policy via
    ``formats_for`` before calling ``emit``.

    Parameters
    ----------
    item : ExportItem
        The canonical content + provenance to emit.
    fmt : str
        One of ``EXPORT_FORMATS``. Unknown → ``ValueError``.
    keypair : Keypair, optional
        Required for the signed formats (``antiek``, ``antiek_html``); the
        unsigned HTML projection needs none.

    Returns
    -------
    bytes | str
        ``"html"`` → str (script-free projection).
        ``"antiek"`` → bytes (signed ``.antiek`` container).
        ``"antiek_html"`` → str (signed single-file HTML).

    Raises
    ------
    ValueError
        Unknown format, or a signed format called with ``keypair=None``.
    """
    if fmt == "html":
        # No keypair: an HTML projection is an unsigned, derived artifact.
        return render(_doc_model(item), RenderContext())

    if fmt == "antiek":
        if keypair is None:
            raise ValueError(
                "emit: format 'antiek' requires a keypair (signed container); "
                "got keypair=None"
            )
        # created_at is pinned so the signed manifest is byte-stable across
        # calls — parity. WriterInput carries only canonical + provenance fields.
        return write_antiek(
            WriterInput(
                notebook_id=item.notebook_id,
                user_id=item.user_id,
                document_id=item.document_id,
                parent_document_id=item.parent_document_id,
                content_class=item.content_class,
                title=item.title,
                content_tiptap=item.content_tiptap,
                created_at=_FIXED_CREATED_AT,
            ),
            keypair=keypair,
        )

    if fmt == "antiek_html":
        if keypair is None:
            raise ValueError(
                "emit: format 'antiek_html' requires a keypair (signed "
                "single-file); got keypair=None"
            )
        # Render the projection, then sign it as a single self-contained file.
        projection = render(_doc_model(item), RenderContext())
        return build_single_file(projection, keypair=keypair)

    raise ValueError(
        f"emit: unknown format {fmt!r}; valid: {list(EXPORT_FORMATS)}"
    )


def _doc_model(item: ExportItem) -> dict:
    """The doc-model the renderer + island consume: the TipTap content array,
    the title, and an empty edges appendix. The ``ExportItem`` intentionally
    carries no edges — ``emit`` projects canonical content; an empty edges list
    is the honest empty state (the renderer renders no edges appendix then)."""
    return {
        "content": item.content_tiptap.get("content", []),
        "title": item.title,
        "edges": [],
    }


__all__ = [
    "EXPORT_FORMATS",
    "SURFACE_FORMATS",
    "ExportItem",
    "emit",
    "formats_for",
]
