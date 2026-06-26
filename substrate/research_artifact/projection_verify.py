"""Mechanical checks for ResearchArtifact HTML KB projections.

Used by goal harness step 3 and ``scripts/goal_harness_deliverables.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .import_notes import parse_body_from_html
from .render import render_html
from .schema import ResearchArtifactBody

_EXECUTABLE_SCRIPT_RE = re.compile(
    r"<script(?![^>]*\btype\s*=\s*['\"]application/json['\"])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProjectionCheckResult:
    ok: bool
    no_executable_scripts: bool
    has_provenance: bool
    roundtrip_match: bool
    detail: str


def has_executable_scripts(html: str) -> bool:
    return bool(_EXECUTABLE_SCRIPT_RE.search(html))


def has_provenance_markers(html: str) -> bool:
    return (
        'id="antiek-artifact-v1"' in html
        and ("data-node-id" in html or "data-investigation-id" in html)
    )


def roundtrip_body(
    body: ResearchArtifactBody, *, interactive: bool = False
) -> ResearchArtifactBody:
    html = render_html(body, interactive=interactive)
    return parse_body_from_html(html)


def verify_kb_projection(body: ResearchArtifactBody) -> ProjectionCheckResult:
    html = render_html(body, interactive=False)
    no_exec = not has_executable_scripts(html)
    prov = has_provenance_markers(html)
    rt = roundtrip_body(body, interactive=False)
    roundtrip_ok = rt.model_dump(mode="json") == body.model_dump(mode="json")
    ok = no_exec and prov and roundtrip_ok and len(html.strip()) > 0
    detail = json.dumps(
        {"bytes": len(html.encode("utf-8")), "content_hash": body.content_hash()}
    )
    return ProjectionCheckResult(
        ok=ok,
        no_executable_scripts=no_exec,
        has_provenance=prov,
        roundtrip_match=roundtrip_ok,
        detail=detail,
    )