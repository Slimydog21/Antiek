"""Closed secret-free source coverage shared by synthesis and HTML artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SOURCES = ("exa", "parallel", "arxiv", "substack")


class ArtifactSourceReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["exa", "parallel", "arxiv", "substack"]
    succeeded_leaves: int = Field(ge=0)
    total_leaves: int = Field(ge=1)


class ArtifactLeafSourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["exa", "parallel", "arxiv", "substack"]
    status: Literal["succeeded", "failed", "skipped"]
    document_count: int = Field(ge=0, le=50)


class ArtifactLeafCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str = Field(min_length=1, max_length=512)
    sources: list[ArtifactLeafSourceStatus] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _validate_sources(self) -> ArtifactLeafCoverage:
        if tuple(item.source for item in self.sources) != _SOURCES:
            raise ValueError("artifact leaf sources must use canonical source order")
        return self


class ArtifactSourceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["authorized_multi_source"]
    evidence_complete: Literal[True]
    partial: bool
    partial_leaf_investigation_ids: list[str] = Field(default_factory=list, max_length=100)
    sources: list[ArtifactSourceReceipt] = Field(min_length=4, max_length=4)
    leaves: list[ArtifactLeafCoverage] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _validate_coverage(self) -> ArtifactSourceCoverage:
        if tuple(item.source for item in self.sources) != _SOURCES:
            raise ValueError("artifact sources must use canonical source order")
        totals = {item.total_leaves for item in self.sources}
        if len(totals) != 1 or any(
            item.succeeded_leaves > item.total_leaves for item in self.sources
        ):
            raise ValueError("artifact source counts are inconsistent")
        if self.partial != bool(self.partial_leaf_investigation_ids):
            raise ValueError("artifact partial truth must match affected leaves")
        if len(set(self.partial_leaf_investigation_ids)) != len(
            self.partial_leaf_investigation_ids
        ):
            raise ValueError("artifact partial leaves must be unique")
        leaf_ids = [leaf.investigation_id for leaf in self.leaves]
        if len(set(leaf_ids)) != len(leaf_ids):
            raise ValueError("artifact coverage leaves must be unique")
        total = next(iter(totals))
        if len(self.leaves) != total:
            raise ValueError("artifact leaf matrix must match aggregate total")
        expected_partial = sorted(
            leaf.investigation_id
            for leaf in self.leaves
            if any(item.status != "succeeded" for item in leaf.sources)
        )
        if sorted(self.partial_leaf_investigation_ids) != expected_partial:
            raise ValueError("artifact affected leaves must match source statuses")
        expected_successes = {
            source: sum(leaf.sources[index].status == "succeeded" for leaf in self.leaves)
            for index, source in enumerate(_SOURCES)
        }
        if any(item.succeeded_leaves != expected_successes[item.source] for item in self.sources):
            raise ValueError("artifact aggregate counts must match leaf statuses")
        return self


class ArtifactInheritedReuseUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: str = Field(min_length=1, max_length=512)
    source_investigation_id: str = Field(min_length=1, max_length=512)
    state: Literal["complete", "partial", "unknown"]
    source_successes: tuple[int, int, int, int]
    total_leaves: int = Field(ge=0, le=100)
    partial_leaf_count: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _validate_qualification(self) -> ArtifactInheritedReuseUnit:
        SourceCoverageQualification(
            state=self.state,
            source_successes=self.source_successes,
            total_leaves=self.total_leaves,
            partial_leaf_count=self.partial_leaf_count,
        )
        return self


class ArtifactLeafInheritedReuse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    investigation_id: str = Field(min_length=1, max_length=512)
    state: Literal[
        "not_attempted", "attempted_zero", "qualified", "legacy_unqualified"
    ]
    injected_unit_count: int = Field(ge=0, le=100)
    injected_unit_ids: tuple[str, ...] = Field(
        default=(), max_length=100, exclude_if=lambda value: not value
    )
    qualifications: tuple[ArtifactInheritedReuseUnit, ...] = Field(
        default=(), max_length=100
    )

    @model_validator(mode="after")
    def _validate_state(self) -> ArtifactLeafInheritedReuse:
        if len(set(self.injected_unit_ids)) != len(self.injected_unit_ids):
            raise ValueError("injected inherited reuse unit IDs must be unique")
        if self.injected_unit_ids and len(self.injected_unit_ids) != self.injected_unit_count:
            raise ValueError("injected inherited reuse IDs must match injected count")
        if self.state in {"not_attempted", "attempted_zero"}:
            if self.injected_unit_count or self.injected_unit_ids or self.qualifications:
                raise ValueError(f"{self.state} cannot claim injected units")
        elif self.state == "legacy_unqualified":
            if self.injected_unit_count == 0 or self.qualifications:
                raise ValueError("legacy unqualified reuse requires an unqualified injection")
        elif (
            self.injected_unit_count == 0
            or len(self.qualifications) != self.injected_unit_count
        ):
            raise ValueError("qualified reuse requires one qualification per injected unit")
        unit_ids = [unit.unit_id for unit in self.qualifications]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("inherited reuse unit IDs must be unique within a leaf")
        if self.injected_unit_ids and tuple(unit_ids) not in ((), self.injected_unit_ids):
            raise ValueError("inherited qualifications must match injected unit IDs")
        return self


class ArtifactInheritedReuse(BaseModel):
    """Secret-free inherited knowledge provenance, distinct from direct evidence."""

    model_config = ConfigDict(extra="forbid")
    leaves: tuple[ArtifactLeafInheritedReuse, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def _validate_leaves(self) -> ArtifactInheritedReuse:
        ids = [leaf.investigation_id for leaf in self.leaves]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("inherited reuse leaves must be unique and sorted")
        return self


class ArchivedSourceCoverageEnvelope(BaseModel):
    """Immutable terminal provenance binding for one evidence pack."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2, 3] = 1
    pack_schema_version: Literal[2, 3, 4] = 2
    pack_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gather_plan_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    coverage: ArtifactSourceCoverage | None = None
    inherited_reuse: ArtifactInheritedReuse | None = None
    claim_support_by_chunk: dict[str, tuple[str, ...]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    claim_support_leaf_by_chunk: dict[str, str] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def _validate_version(self) -> ArchivedSourceCoverageEnvelope:
        if self.schema_version == 1 and (
            self.pack_schema_version != 2
            or self.inherited_reuse is not None
            or self.coverage is None
            or self.gather_plan_fingerprint is None
        ):
            raise ValueError("terminal provenance v1 cannot carry inherited reuse")
        if self.schema_version == 2 and (
            self.pack_schema_version != 3 or self.inherited_reuse is None
        ):
            raise ValueError("terminal provenance v2 requires pack v3 inherited reuse")
        if self.schema_version == 3 and (
            self.pack_schema_version != 4 or self.inherited_reuse is None
        ):
            raise ValueError("terminal provenance v3 requires pack v4 inherited reuse")
        if self.schema_version < 3 and (
            self.claim_support_by_chunk or self.claim_support_leaf_by_chunk
        ):
            raise ValueError("terminal provenance v1/v2 cannot carry claim support lineage")
        if len(self.claim_support_by_chunk) > 1000:
            raise ValueError("claim support chunk map exceeds policy limit")
        leaves = {
            leaf.investigation_id: leaf
            for leaf in self.inherited_reuse.leaves
        } if self.inherited_reuse is not None else {}
        if set(self.claim_support_by_chunk) != set(self.claim_support_leaf_by_chunk):
            raise ValueError("claim support maps must contain the same chunk IDs")
        for chunk_id, unit_ids in self.claim_support_by_chunk.items():
            if not chunk_id.strip() or len(chunk_id) > 512:
                raise ValueError("claim support map contains an invalid chunk ID")
            if len(unit_ids) > 100 or len(set(unit_ids)) != len(unit_ids):
                raise ValueError("claim support map contains duplicate or excessive unit IDs")
            leaf_id = self.claim_support_leaf_by_chunk[chunk_id]
            leaf = leaves.get(leaf_id)
            if leaf is None:
                raise ValueError("claim support map references an unavailable leaf")
            available_units = set(leaf.injected_unit_ids) or {
                unit.unit_id for unit in leaf.qualifications
            }
            if any(unit_id not in available_units for unit_id in unit_ids):
                raise ValueError("claim support map cites unavailable inherited unit")
        if self.schema_version in {2, 3} and (
            (self.coverage is None) != (self.gather_plan_fingerprint is None)
        ):
            raise ValueError("direct coverage and gather fingerprint must appear together")
        return self


def validate_archived_claim_support(
    envelope: ArchivedSourceCoverageEnvelope,
    thesis: object,
    *,
    manifest_chunk_ids: set[str],
) -> None:
    """Fail closed when archived thesis lineage can be mixed with another pack."""
    if envelope.schema_version < 3:
        return
    if not isinstance(thesis, dict):
        raise ValueError("terminal provenance v3 requires a structured thesis")
    components = thesis.get("thesis_components")
    if not isinstance(components, list):
        raise ValueError("terminal provenance v3 thesis lacks components")
    reasoning_paths = thesis.get("reasoning_paths_used", [])
    if not isinstance(reasoning_paths, list):
        raise ValueError("terminal provenance v3 thesis has malformed reasoning paths")
    insufficient = thesis.get("implicit_recommendation") == "insufficient_evidence"
    if set(envelope.claim_support_by_chunk) - manifest_chunk_ids:
        raise ValueError("claim support map contains chunks outside the archive manifest")
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("terminal thesis component is malformed")
        chunk_ids = component.get("supporting_chunk_ids", [])
        unit_ids = component.get("supporting_inherited_unit_ids", [])
        path_indices = component.get("supporting_path_indices", [])
        if (
            not isinstance(chunk_ids, list)
            or not isinstance(unit_ids, list)
            or not isinstance(path_indices, list)
        ):
            raise ValueError("terminal thesis claim support is malformed")
        if not chunk_ids and not path_indices and not insufficient:
            raise ValueError("terminal thesis component lacks structural provenance")
        for path_index in path_indices:
            if (
                not isinstance(path_index, int)
                or isinstance(path_index, bool)
                or path_index < 0
                or path_index >= len(reasoning_paths)
                or not isinstance(reasoning_paths[path_index], dict)
                or not isinstance(reasoning_paths[path_index].get("path_node_ids"), list)
                or not reasoning_paths[path_index]["path_node_ids"]
            ):
                raise ValueError("terminal thesis cites an invalid reasoning path")
        if any(chunk_id not in manifest_chunk_ids for chunk_id in chunk_ids):
            raise ValueError("terminal thesis cites a chunk outside the archive manifest")
        reachable = {
            unit_id
            for chunk_id in chunk_ids
            for unit_id in envelope.claim_support_by_chunk.get(chunk_id, ())
        }
        if any(unit_id not in reachable for unit_id in unit_ids):
            raise ValueError("terminal thesis cites unreachable inherited support")


# ---------------------------------------------------------------------------
# SPR-DRL-19 — compact reuse coverage qualification
# ---------------------------------------------------------------------------


class SourceCoverageQualificationValidationError(ValueError):
    """Raised when a SourceCoverageQualification fails validation."""


@dataclass(frozen=True)
class SourceCoverageQualification:
    """Compact, immutable, closed reuse-source-coverage qualification.

    Carries the state (complete / partial / unknown), canonical per-source
    success ratios, and partial-leaf count. No provider receipt, endpoint,
    cost, key, feed, query, or error prose.

    ``complete``: every source succeeded for every leaf.
    ``partial``: at least one source/leaf combination failed; partial_leaf_count > 0.
    ``unknown``: the archive cannot certify the unit's source coverage.

    Validation rejects: negative/overflow counts, noncanonical source order,
    contradictory complete/partial state, and success > total for any source.
    """

    state: Literal["complete", "partial", "unknown"]
    source_successes: tuple[int, int, int, int]  # canonical order: exa, parallel, arxiv, substack
    total_leaves: int
    partial_leaf_count: int = 0

    def __post_init__(self) -> None:
        if self.state not in ("complete", "partial", "unknown"):
            raise SourceCoverageQualificationValidationError(f"invalid state: {self.state!r}")
        if len(self.source_successes) != 4:
            raise SourceCoverageQualificationValidationError(
                "source_successes must have exactly 4 entries (canonical order)"
            )
        for i, count in enumerate(self.source_successes):
            if count < 0:
                raise SourceCoverageQualificationValidationError(
                    f"negative source success count at index {i}: {count}"
                )
            if self.total_leaves >= 0 and count > self.total_leaves:
                raise SourceCoverageQualificationValidationError(
                    f"source success count {count} exceeds total_leaves {self.total_leaves} "
                    f"at index {_SOURCES[i]}"
                )
        if self.total_leaves < 0:
            raise SourceCoverageQualificationValidationError(
                f"negative total_leaves: {self.total_leaves}"
            )
        if self.total_leaves > 100:
            raise SourceCoverageQualificationValidationError(
                "total_leaves exceeds the archived coverage bound of 100"
            )
        if self.partial_leaf_count < 0:
            raise SourceCoverageQualificationValidationError(
                f"negative partial_leaf_count: {self.partial_leaf_count}"
            )
        if self.partial_leaf_count > self.total_leaves:
            raise SourceCoverageQualificationValidationError(
                f"partial_leaf_count {self.partial_leaf_count} exceeds "
                f"total_leaves {self.total_leaves}"
            )
        # Contradictory state: complete with partial leaves, or partial without them
        if self.state == "complete" and self.partial_leaf_count > 0:
            raise SourceCoverageQualificationValidationError(
                "complete state cannot have partial_leaf_count > 0"
            )
        if self.state == "partial" and self.partial_leaf_count == 0:
            raise SourceCoverageQualificationValidationError(
                "partial state requires partial_leaf_count > 0"
            )
        if self.state == "unknown" and self.partial_leaf_count > 0:
            raise SourceCoverageQualificationValidationError(
                "unknown state cannot have partial_leaf_count > 0"
            )
        if self.state == "unknown" and (
            self.total_leaves != 0 or any(self.source_successes)
        ):
            raise SourceCoverageQualificationValidationError(
                "unknown state cannot claim source coverage counts"
            )
        if self.state == "complete" and (
            self.total_leaves == 0
            or any(count != self.total_leaves for count in self.source_successes)
        ):
            raise SourceCoverageQualificationValidationError(
                "complete state requires every source to cover every leaf"
            )
        if self.state == "partial" and (
            self.total_leaves == 0
            or all(count == self.total_leaves for count in self.source_successes)
        ):
            raise SourceCoverageQualificationValidationError(
                "partial state requires an incomplete source ratio"
            )

    @property
    def source_ratios(self) -> tuple[str, str, str, str]:
        """Canonical per-source success ratios as 'succeeded/total' strings."""
        return tuple(
            f"{s}/{self.total_leaves}" if self.total_leaves > 0 else "0/0"
            for s in self.source_successes
        )  # type: ignore[return-value]

    @classmethod
    def from_envelope(cls, envelope: ArchivedSourceCoverageEnvelope) -> SourceCoverageQualification:
        """Derive a qualification from an archived source coverage envelope."""
        cov = envelope.coverage
        if cov is None:
            raise SourceCoverageQualificationValidationError(
                "terminal provenance has no direct source coverage"
            )
        source_successes = tuple(
            next(r.succeeded_leaves for r in cov.sources if r.source == src) for src in _SOURCES
        )
        total = cov.sources[0].total_leaves
        partial_count = len(cov.partial_leaf_investigation_ids)
        if not cov.partial and partial_count == 0 and all(s == total for s in source_successes):
            state: Literal["complete", "partial", "unknown"] = "complete"
        elif cov.partial:
            state = "partial"
        else:
            state = "partial"
        return cls(
            state=state,
            source_successes=source_successes,  # type: ignore[arg-type]
            total_leaves=total,
            partial_leaf_count=partial_count,
        )

    @classmethod
    def unknown(cls) -> SourceCoverageQualification:
        """The default qualification for units without archive evidence."""
        return cls(
            state="unknown",
            source_successes=(0, 0, 0, 0),
            total_leaves=0,
            partial_leaf_count=0,
        )
