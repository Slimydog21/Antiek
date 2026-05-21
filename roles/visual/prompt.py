"""Visual role — prompts + context shape.

The role is given one frame (still image or extracted video frame)
plus optional surrounding-document context. It must produce a JSON
object with a list of ``claims``, each grounded in an explicit
``region`` of the frame.

Voice discipline (master-spec §5) applies: the role's prose stays
short, no "the image shows" filler, no narration. Claims are
declarative statements about what is depicted; one claim per
distinct observation; uncertain observations land in
``uncited_observations`` with the same shape minus the region.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Bump when the prompt itself changes. Reads by the substrate's
# event log so old + new outputs are distinguishable in trajectories.
VISUAL_PROMPT_VERSION = "visual-v1"

# Verifier tier — claim extraction needs cross-family corroboration
# semantics (substrate-grounding invariant: every visual claim must
# trace to a concrete region). Per master-spec §C, verify tier is
# the right cost / accuracy point for grounding-heavy work.
VISUAL_TIER = "verify"

# Low temperature. Claim extraction is deterministic; creative tasks
# go to other roles (creative_writer, thought_partner).
VISUAL_TEMPERATURE = 0.1


VISUAL_SYSTEM_PROMPT = """You are the substrate's visual role.

Given a single frame (still image or a video frame extracted at a
specific timestamp), extract DECLARATIVE CLAIMS about what is
depicted. Each claim must be grounded in a concrete REGION of the
frame — a bounding box in normalized [0, 1] coordinates.

Output is JSON only, conforming exactly to:

{
  "frame_summary": "<one short declarative sentence>",
  "claims": [
    {
      "claim_text": "<declarative observation>",
      "confidence": "low" | "moderate" | "high",
      "region": {
        "page_or_frame_id": "<string, echo the input>",
        "bbox": [x_min, y_min, x_max, y_max]
      }
    }
  ],
  "uncited_observations": [
    {
      "claim_text": "<observation without a confident region>",
      "confidence": "low"
    }
  ]
}

Rules:
- claim_text is one declarative sentence, no narration.
- bbox values are floats in [0, 1].
- confidence is one of "low" | "moderate" | "high".
- The frame_summary is single sentence; no "the image shows".
- uncited_observations is optional; omit the key if empty.

Do NOT add prose outside the JSON object. The substrate parses the
JSON and refuses any extra commentary."""


@dataclass(frozen=True)
class VisualFrame:
    """One frame to analyze. ``image_url`` is the substrate's stable
    handle (e.g. ``data:`` URL or a signed object-store URL). For
    video, ``frame_timestamp_ms`` carries the source-clip timestamp;
    for stills, leave it None."""

    image_url: str
    page_or_frame_id: str
    frame_timestamp_ms: Optional[int] = None
    frame_width_px: Optional[int] = None
    frame_height_px: Optional[int] = None


@dataclass(frozen=True)
class VisualContext:
    """Context pack passed to the visual role. Carries the frame plus
    optional surrounding document text (e.g. caption, paragraph the
    frame appears beside) so the role can disambiguate."""

    document_id: str
    frame: VisualFrame
    surrounding_text: Optional[str] = None


VISUAL_USER_TEMPLATE = """Document: {document_id}
Frame: {page_or_frame_id}{frame_timestamp_hint}{frame_dimensions_hint}

Frame URL: {image_url}
{surrounding_text_section}
Produce the JSON object specified in the system prompt."""


def _hint_or_blank(value: Optional[object], label: str) -> str:
    if value is None:
        return ""
    return f"\n{label}: {value}"


def render_user_template(ctx: VisualContext) -> str:
    """Render the user-side prompt by interpolating the context."""
    frame = ctx.frame
    surrounding = ""
    if ctx.surrounding_text:
        surrounding = (
            f"\nSurrounding document text:\n{ctx.surrounding_text.strip()}\n"
        )
    dim_hint = ""
    if frame.frame_width_px and frame.frame_height_px:
        dim_hint = (
            f"\nFrame dimensions: "
            f"{frame.frame_width_px}x{frame.frame_height_px} px"
        )
    return VISUAL_USER_TEMPLATE.format(
        document_id=ctx.document_id,
        page_or_frame_id=frame.page_or_frame_id,
        frame_timestamp_hint=_hint_or_blank(
            frame.frame_timestamp_ms, "Frame timestamp (ms)",
        ),
        frame_dimensions_hint=dim_hint,
        image_url=frame.image_url,
        surrounding_text_section=surrounding,
    )


def render_full_prompt(ctx: VisualContext) -> dict[str, str]:
    """Materialize the system + user pair for dispatch. The dispatch
    layer expects this shape; provider adapters translate it."""
    return {
        "system": VISUAL_SYSTEM_PROMPT,
        "user": render_user_template(ctx),
    }


__all__ = [
    "VISUAL_PROMPT_VERSION",
    "VISUAL_SYSTEM_PROMPT",
    "VISUAL_TEMPERATURE",
    "VISUAL_TIER",
    "VISUAL_USER_TEMPLATE",
    "VisualContext",
    "VisualFrame",
    "render_full_prompt",
    "render_user_template",
]
