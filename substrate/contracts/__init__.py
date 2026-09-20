"""``substrate.contracts`` — the integration backbone (antiek-unified SPR-01).

Typed interfaces (field shapes only, no behavior) that the four product
workflows — Research (DRW), Read, Write, Speak — build and test against, plus
the frozen DRW sprint-lock, the cross-spec dependency DAG, and the conformance
harness. This is the **keystone**: SPR-02 through SPR-08 and all four product
specs reference it. A downstream instance imports a contract type from here;
it never re-derives the shape.

The rule for the whole package: **one owner per layer, every workflow a
consumer, never a fork.** DRW owns the shared primitives (insight/question
nodes, note-taker, reading surface); the contracts here are the interface the
owner's implementation conforms to and the consumers compose against. The
frozen sprint-lock + the SPR-08 conformance gate keep that contract safe while
45 sprints land across parallel Claude Code instances.

Contract status:

* COMMITTED — the implementation exists; the shape is pinned.
* PROVISIONAL — the owner (typically a not-yet-landed DRW sprint) has not
  pinned the shape; marked so the SPR-08 conformance harness treats it as
  not-yet-load-bearing. Today: ``ReaderSurfaceContract`` (DRW SPR-10) and the
  Speak interviewer shapes.

See ``inventory.md`` for the full row-by-row map (contract · owning spec+sprint
· consumers · status), and ``docs/decisions/tech-stack-ledger.md`` for the
cross-cutting tech-stack commitments this sprint closes.
"""

from __future__ import annotations

from .accrual import AccrualContract, AccrualSource
from .conformance import (
    ConformanceError,
    ConformanceResult,
    assert_conformance,
    verify_conformance,
)
from .context_pack import AssembledLayerContract, ContextPackContract
from .drw_sprint_lock import (
    DRW_SPRINTS,
    LOCK_VERSION,
    Deliverable,
    cited_sprints,
    downstream_citations,
    resolve_drw_sprint,
    verify_citations_resolve,
)
from .interviewer import (
    ConsentContract,
    EconomicsCellContract,
    InterviewerResultContract,
)
from .multimedia import (
    ALLOWED_STATUS_TRANSITIONS,
    ClaimToChunk,
    CostRow,
    EvidenceDerivation,
    EvidenceSpan,
    GeneratedFile,
    MediaSegment,
    MultimediaAssetContract,
    MultimediaManifest,
    MultimediaStatus,
    PromptRecord,
    ProviderCall,
    ScriptLine,
    SourceCitation,
    can_transition,
)
from .nodes import (
    InsightNodeContract,
    KnowledgeUnitContract,
    ProvenanceLink,
    QuestionNodeContract,
    ServabilityTag,
)
from .note_taker import NoteTakerOutputContract
from .outline_block import OutlineBlockContract
from .reading_surface import ReaderSurfaceContract
from .research_runner import ResearchRunner, StepEvent
from .servable import ServableEntryContract
from .voice_pipeline import (
    VOICE_INGEST_FUNCTION,
    VOICE_NOTE_DOCUMENT_TYPE,
    VOICE_PIPELINE_OWNER,
    VoicePipelineContract,
)

# Bump on ANY change to a committed contract's field shape; mirrors
# ``EVENT_SCHEMA_VERSION``. The codegen staleness check ties the generated TS
# (``apps/reading/src/generated/contracts.ts``) to this version.
CONTRACT_SCHEMA_VERSION: int = 3

# Pydantic contract models that go through TS codegen (provisional Protocols —
# ReaderSurfaceContract, VoicePipelineContract — are excluded; they carry
# behavior, not data).
CODEGEN_CONTRACTS: tuple[type, ...] = (
    InsightNodeContract,
    QuestionNodeContract,
    NoteTakerOutputContract,
    ContextPackContract,
    AssembledLayerContract,
    OutlineBlockContract,
    ServableEntryContract,
    AccrualContract,
    InterviewerResultContract,
    ConsentContract,
    EconomicsCellContract,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    # node contracts
    "InsightNodeContract",
    "QuestionNodeContract",
    # multimedia category contract (Python-first until workstation codegen)
    "ALLOWED_STATUS_TRANSITIONS",
    "ClaimToChunk",
    "CostRow",
    "EvidenceDerivation",
    "EvidenceSpan",
    "GeneratedFile",
    "MediaSegment",
    "MultimediaAssetContract",
    "MultimediaManifest",
    "MultimediaStatus",
    "PromptRecord",
    "ProviderCall",
    "ScriptLine",
    "SourceCitation",
    "can_transition",
    # AFF SPR-04 — knowledge-unit deposit contract (extension of the node
    # contracts above). Python-only for now: NOT added to CODEGEN_CONTRACTS /
    # CONTRACT_MODELS because the first TS consumer is SPR-06 (retrieval);
    # emitting it now would bump CONTRACT_SCHEMA_VERSION + contracts.ts for a
    # consumer that does not yet exist. See spr-04 decision doc.
    "KnowledgeUnitContract",
    "ProvenanceLink",
    "ServabilityTag",
    "NoteTakerOutputContract",
    "ContextPackContract",
    "AssembledLayerContract",
    "ReaderSurfaceContract",
    "VoicePipelineContract",
    "VOICE_PIPELINE_OWNER",
    "VOICE_NOTE_DOCUMENT_TYPE",
    "VOICE_INGEST_FUNCTION",
    "OutlineBlockContract",
    "ServableEntryContract",
    "AccrualContract",
    "AccrualSource",
    "InterviewerResultContract",
    "ConsentContract",
    "EconomicsCellContract",
    # research-runner protocol (re-exported from DRW SPR-02)
    "ResearchRunner",
    "StepEvent",
    # frozen DRW sprint-lock
    "DRW_SPRINTS",
    "LOCK_VERSION",
    "Deliverable",
    "resolve_drw_sprint",
    "downstream_citations",
    "cited_sprints",
    "verify_citations_resolve",
    # conformance harness
    "verify_conformance",
    "assert_conformance",
    "ConformanceResult",
    "ConformanceError",
    # codegen surface
    "CODEGEN_CONTRACTS",
]
