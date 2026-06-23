"""Phase 8 knowledge-extraction + skill-patching primitives (Sprint 6
day 2-3 migration of Researchmaxx ``knowledge_extraction.py``, 690 LOC).

Phase 8 is the **compounding mechanism** — every successful synthesis
that matches one or more domain keyword lists feeds extracted durable
findings back into the matching ``SKILL.md``. The substrate's
``orchestration/phase_log/`` (Sprint 5 day 3-4) is the gate that
enforces this happened; this module is what runs INSIDE that gate.

Four pieces:

- ``keywords`` — ``DOMAIN_KEYWORDS`` + ``classify_domains`` pure
  function. Single keyword hit ⇒ matched.
- ``extraction_prompt`` — ``EXTRACTION_SYSTEM_PROMPT`` +
  ``EXTRACTION_USER_TEMPLATE`` + ``make_extraction_prompt`` builder.
  Closed section vocabulary + closed confidence-tier set.
- ``patch`` — ``find_section_boundaries`` / ``format_finding_bullet``
  / ``apply_finding_to_section`` pure functions; ``patch_skill`` at
  the file-system boundary. ``ANTIEK_KNOWLEDGE_SKILLS_DIR`` overrides
  the default root.
- ``extract`` — ``extract_and_patch`` orchestrator with injectable
  ``LLMCall``. ``default_llm_call_factory`` wires
  ``substrate.dispatch`` in production; tests pass a stub. Two-tier
  JSON parse + one-shot repair retry preserved
  (``ANTIEK_KE_REPAIR_ENABLED``).

What's deferred:

- ``KE_LLM_RESPONSE_FAILED`` typed telemetry payload — failures
  currently print to stderr. Sprint 6 day 3-4 will add it alongside
  ``RubricScoredPayload`` wiring so the trajectory carries both
  verification + Phase 8 forensics.
- Phase 8 verifier glue — ``orchestration/phase_log/PhaseLog.verify(8)``
  reads ``result.any_patched`` as evidence. That wiring lands in the
  phase-runner migration (Sprint 7).
"""

from .auto_patch import (
    AUTO_PATCH_DOMAIN_KEYWORDS,
    already_patched,
    patch_from_synthesis,
    patch_skill_file,
    render_patch,
    route_domains,
)
from .auto_patch import (
    SECTION_MARKER as AUTO_PATCH_SECTION_MARKER,
)
from .auto_patch import (
    SECTION_PREAMBLE as AUTO_PATCH_SECTION_PREAMBLE,
)
from .extract import (
    ExtractionResult,
    LLMCall,
    default_llm_call_factory,
    extract_and_patch,
    extract_findings,
)
from .extraction_prompt import (
    EXTRACTION_CONFIDENCE_TIERS,
    EXTRACTION_SECTIONS,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    make_extraction_prompt,
)
from .keywords import DOMAIN_KEYWORDS, classify_domains
from .master_md import (
    DEFAULT_FILENAME as MASTER_MD_DEFAULT_FILENAME,
)
from .master_md import (
    SYNTHESIS_ID_MARKER,
    build_master_md,
    default_research_base,
    existing_marker_matches,
    generate_master_md,
    slugify,
)
from .patch import (
    PLACEHOLDER_TEXT,
    apply_finding_to_section,
    default_skills_root,
    find_section_boundaries,
    format_finding_bullet,
    patch_skill,
)

__all__ = [
    # keywords
    "DOMAIN_KEYWORDS",
    "classify_domains",
    # extraction_prompt
    "EXTRACTION_SECTIONS",
    "EXTRACTION_CONFIDENCE_TIERS",
    "EXTRACTION_SYSTEM_PROMPT",
    "EXTRACTION_USER_TEMPLATE",
    "make_extraction_prompt",
    # patch
    "PLACEHOLDER_TEXT",
    "default_skills_root",
    "find_section_boundaries",
    "format_finding_bullet",
    "apply_finding_to_section",
    "patch_skill",
    # extract
    "LLMCall",
    "ExtractionResult",
    "extract_findings",
    "extract_and_patch",
    "default_llm_call_factory",
    # master_md
    "SYNTHESIS_ID_MARKER",
    "MASTER_MD_DEFAULT_FILENAME",
    "default_research_base",
    "slugify",
    "build_master_md",
    "existing_marker_matches",
    "generate_master_md",
    # auto_patch
    "AUTO_PATCH_DOMAIN_KEYWORDS",
    "AUTO_PATCH_SECTION_MARKER",
    "AUTO_PATCH_SECTION_PREAMBLE",
    "route_domains",
    "already_patched",
    "render_patch",
    "patch_skill_file",
    "patch_from_synthesis",
]
