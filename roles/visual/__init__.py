"""Visual role — Sprint 30+ thread 4.

Image + video frame analysis. Extends the substrate's role roster
from twelve to thirteen. Per the Sprint 30+ breakdown thread 4:
*"Image-and-video ingestion expands beyond timestamps into actual
frame-level analysis. A new substrate role joins the existing twelve.
Useful for biography-as-acquisition and any source corpus where the
visual is part of the argument."*

The visual role takes a frame (URL pointer to an image; for video,
one frame extracted at a timestamp) and produces a list of
``VisualClaim`` records. Each claim is grounded in a region of the
frame (a bounding box) so the substrate's grounding discipline (§5,
master-spec) holds at the visual layer too: every claim must trace
to a concrete part of a concrete frame, not "the image".

What this scaffold ships:

  - Prompt + temperature + tier constants (substrate-only; no model
    wiring — production injects the VLM via the dispatch protocol).
  - Closed-vocabulary parser for the role's JSON output.
  - Frozen dataclasses for the input context and output result.

What is NOT in this scaffold (deferred to a follow-up sprint):

  - Bridge handler that listens for a ``frame.identified`` event,
    runs dispatch, and emits a typed ``visual.claims_extracted``
    event. (Substrate event vocabulary doesn't yet have a
    ``visual.*`` family; adding it lands with the bridge.)
  - Video-frame extraction pipeline (ffmpeg + frame-rate decisions).
    The role accepts a single still frame; the upstream "pick the
    interesting frame" question is a separate substrate concern.
  - Concrete VLM provider integration (GPT-4V, Claude vision,
    Gemini-Pro-Vision). The dispatch protocol abstracts this; the
    role is provider-agnostic.

Audit posture: per master-spec §5 voice discipline, the role's
output is constrained — no "the image shows..." filler — and the
parser refuses prose that doesn't conform to the JSON contract.
The temperature is low (claim extraction is not creative writing).
"""

from .parser import (
    VisualClaim,
    VisualRegion,
    VisualResult,
    VisualValidationError,
    parse_visual_response,
)
from .prompt import (
    VISUAL_PROMPT_VERSION,
    VISUAL_SYSTEM_PROMPT,
    VISUAL_TEMPERATURE,
    VISUAL_TIER,
    VISUAL_USER_TEMPLATE,
    VisualContext,
    VisualFrame,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    "VISUAL_PROMPT_VERSION",
    "VISUAL_SYSTEM_PROMPT",
    "VISUAL_TEMPERATURE",
    "VISUAL_TIER",
    "VISUAL_USER_TEMPLATE",
    "VisualClaim",
    "VisualContext",
    "VisualFrame",
    "VisualRegion",
    "VisualResult",
    "VisualValidationError",
    "parse_visual_response",
    "render_full_prompt",
    "render_user_template",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=4000,
    expected_output_tokens=1000,
    spawn_pattern_doc=(
        'Pass a visual-spec brief. Returns a single visual artifact (diagram description or image-gen prompt). Single-turn; operator iterates by re-invoking with revised brief.'
    ),
)
