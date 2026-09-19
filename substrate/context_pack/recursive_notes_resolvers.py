"""Canonical resolvers for recursive-note prompt content."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any, cast

from substrate.engagement_spine import EngagementStore
from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.import_notes import parse_body_from_html
from substrate.research_artifact.storage import FilesystemArtifactStore, UnsafeArtifactState

from .recursive_notes import (
    MAX_CANDIDATES,
    MAX_ID_BYTES,
    MAX_REQUEST_ITEMS,
    AdvisoryPreview,
    ContentKind,
    ExclusionReason,
    ExclusionReceipt,
    RecursiveNotesPack,
    _assemble_resolved_notes_pack,
    _ResolvedCandidate,
    account_scope_digest,
    digest_text,
    private_identifier_digest,
)

OwnerResolver = Callable[[str], str | None]
MAX_ADVISORY_BYTES = 65_536
MAX_ADVISORY_ITEMS = 256
MAX_ARTIFACT_HTML_BYTES = 16 * 1024 * 1024
MAX_AGGREGATE_ARTIFACT_HTML_BYTES = 32 * 1024 * 1024


def _opaque_exclusion(
    authority: str,
    identity: str,
    reason: ExclusionReason,
    owner_scope: str,
) -> ExclusionReceipt:
    return ExclusionReceipt(
        authority=authority,
        candidate_digest=private_identifier_digest(identity, owner_scope),
        reason=reason,
        asset_scope_digest=None,
    )


def _valid_request_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and "\x00" not in value
        and len(value.strip().encode("utf-8")) <= MAX_ID_BYTES
    )


def _authorized_assets(
    *,
    authority: str,
    owner_user_id: str,
    asset_ids: Sequence[str],
    asset_owner: OwnerResolver,
) -> tuple[list[str], list[ExclusionReceipt]]:
    if len(asset_ids) > MAX_REQUEST_ITEMS:
        raise ValueError("too many requested assets")
    allowed: list[str] = []
    exclusions: list[ExclusionReceipt] = []
    owner_scope = account_scope_digest(owner_user_id)
    for raw_asset_id in dict.fromkeys(asset_ids):
        if not _valid_request_id(raw_asset_id):
            exclusions.append(
                _opaque_exclusion(authority, repr(raw_asset_id), "malformed", owner_scope)
            )
            continue
        assert isinstance(raw_asset_id, str)
        asset_id = raw_asset_id.strip()
        owner = asset_owner(asset_id)
        if owner is None:
            exclusions.append(
                _opaque_exclusion(authority, asset_id, "missing_asset", owner_scope)
            )
        elif owner != owner_user_id:
            exclusions.append(
                _opaque_exclusion(authority, asset_id, "foreign_owner", owner_scope)
            )
        else:
            allowed.append(asset_id)
    return allowed, exclusions


def _twin_rows(
    *,
    store: EngagementStore,
    asset_id: str,
    explicit_note_ids: set[str],
    owner_scope: str,
) -> tuple[list[_ResolvedCandidate], list[ExclusionReceipt]]:
    candidates: list[_ResolvedCandidate] = []
    exclusions: list[ExclusionReceipt] = []
    try:
        rows = store.list_twins(asset_id)
    # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        # fmt: on
        return [], [
            _opaque_exclusion("engagement_twin", asset_id, "malformed", owner_scope)
        ]
    if not rows:
        return [], [
            _opaque_exclusion("engagement_twin", asset_id, "no_content", owner_scope)
        ]
    if len(rows) > MAX_CANDIDATES:
        rows = rows[:MAX_CANDIDATES]
        exclusions.append(
            _opaque_exclusion(
                "engagement_twin", f"{asset_id}:row-bound", "aggregate_budget", owner_scope
            )
        )
    for ordinal, row in enumerate(rows):
        identity = f"{asset_id}:{ordinal}"
        if not isinstance(row, dict):
            exclusions.append(
                _opaque_exclusion("engagement_twin", identity, "malformed", owner_scope)
            )
            continue
        note_id = str(row.get("note_id") or "")
        kind = str(row.get("kind") or "")
        text = row.get("text")
        if row.get("asset_id") != asset_id or not isinstance(text, str):
            exclusions.append(
                _opaque_exclusion("engagement_twin", identity, "malformed", owner_scope)
            )
            continue
        raw_source_ids = row.get("source_event_ids") or ()
        source_ids = (
            tuple(str(value) for value in raw_source_ids)
            if isinstance(raw_source_ids, (list, tuple))
            else ("",)
        )
        try:
            candidates.append(
                _ResolvedCandidate(
                    authority="engagement_twin",
                    asset_id=asset_id,
                    canonical_id=note_id,
                    kind=cast(ContentKind, kind),
                    text=text,
                    ordinal=ordinal,
                    created_at=(str(row["created_at"]) if row.get("created_at") else None),
                    source_event_ids=source_ids,
                    explicit=note_id in explicit_note_ids,
                )
            )
        except ValueError:
            exclusions.append(
                _opaque_exclusion(
                    "engagement_twin", note_id or identity, "malformed", owner_scope
                )
            )
    return candidates, exclusions


def resolve_twin_candidates(
    *,
    store: EngagementStore,
    owner_user_id: str,
    asset_ids: Sequence[str],
    asset_owner: OwnerResolver,
    explicit_note_ids: Sequence[str] = (),
) -> tuple[list[_ResolvedCandidate], tuple[ExclusionReceipt, ...]]:
    if len(explicit_note_ids) > MAX_REQUEST_ITEMS:
        raise ValueError("too many explicit note ids")
    allowed, exclusions = _authorized_assets(
        authority="engagement_twin",
        owner_user_id=owner_user_id,
        asset_ids=asset_ids,
        asset_owner=asset_owner,
    )
    explicit = {
        value.strip()
        for value in explicit_note_ids
        if isinstance(value, str) and _valid_request_id(value)
    }
    candidates: list[_ResolvedCandidate] = []
    owner_scope = account_scope_digest(owner_user_id)
    for asset_id in allowed:
        resolved, malformed = _twin_rows(
            store=store,
            asset_id=asset_id,
            explicit_note_ids=explicit,
            owner_scope=owner_scope,
        )
        candidates.extend(resolved)
        exclusions.extend(malformed)
        if len(candidates) >= MAX_CANDIDATES:
            candidates = candidates[:MAX_CANDIDATES]
            exclusions.append(
                _opaque_exclusion(
                    "engagement_twin", "candidate-bound", "aggregate_budget", owner_scope
                )
            )
            break
    return candidates, tuple(exclusions)


def resolve_graph_candidates(
    *,
    con: Any,
    store: EngagementStore,
    owner_user_id: str,
    asset_ids: Sequence[str],
    asset_owner: OwnerResolver,
) -> tuple[list[_ResolvedCandidate], tuple[ExclusionReceipt, ...]]:
    owner_scope = account_scope_digest(owner_user_id)
    allowed, exclusions = _authorized_assets(
        authority="depth_graph",
        owner_user_id=owner_user_id,
        asset_ids=asset_ids,
        asset_owner=asset_owner,
    )
    if not allowed:
        return [], tuple(exclusions)
    twin_by_id: dict[str, _ResolvedCandidate] = {}
    for asset_id in allowed:
        twins, malformed = _twin_rows(
            store=store,
            asset_id=asset_id,
            explicit_note_ids=set(),
            owner_scope=owner_scope,
        )
        exclusions.extend(malformed)
        twin_by_id.update({candidate.canonical_id: candidate for candidate in twins})
        if len(twin_by_id) >= MAX_CANDIDATES:
            twin_by_id = dict(list(twin_by_id.items())[:MAX_CANDIDATES])
            exclusions.append(
                _opaque_exclusion(
                    "depth_graph", "twin-bound", "aggregate_budget", owner_scope
                )
            )
            break
    try:
        placeholders = ", ".join("?" for _ in allowed)
        rows = con.execute(
            "SELECT node_id, node_type, canonical_label, metadata, created_at "
            "FROM nodes WHERE node_type IN ('insight', 'question') "
            "AND graph_scope = 'depth' "
            "AND json_extract_string(metadata, '$.twin_asset_id') "
            f"IN ({placeholders}) ORDER BY created_at DESC, node_id "
            f"LIMIT {MAX_CANDIDATES + 1}",
            allowed,
        ).fetchall()
    except Exception:
        return [], tuple(
            exclusions
            + [
                _opaque_exclusion(
                    "depth_graph", "resolver", "resolver_unavailable", owner_scope
                )
            ]
        )
    if len(rows) > MAX_CANDIDATES:
        rows = rows[:MAX_CANDIDATES]
        exclusions.append(
            _opaque_exclusion("depth_graph", "row-bound", "aggregate_budget", owner_scope)
        )
    candidates: list[_ResolvedCandidate] = []
    ordinals: dict[str, int] = {}
    for row_index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 5:
            exclusions.append(
                _opaque_exclusion(
                    "depth_graph", f"row:{row_index}", "malformed", owner_scope
                )
            )
            continue
        node_id, node_type, text, raw_metadata, created_at = row
        try:
            metadata = (
                dict(raw_metadata)
                if isinstance(raw_metadata, dict)
                else json.loads(str(raw_metadata or "{}"))
            )
        # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
        except (TypeError, ValueError, json.JSONDecodeError):
            # fmt: on
            metadata = None
        if not isinstance(metadata, dict):
            exclusions.append(
                _opaque_exclusion("depth_graph", str(node_id), "malformed", owner_scope)
            )
            continue
        asset_id = str(metadata.get("twin_asset_id") or "")
        twin_note_id = str(metadata.get("twin_note_id") or "")
        twin = twin_by_id.get(twin_note_id)
        if (
            metadata.get("origin") != "twin_note"
            or asset_id not in allowed
            or twin is None
            or twin.asset_id != asset_id
            or twin.kind != node_type
            or twin.text != text
        ):
            exclusions.append(
                _opaque_exclusion("depth_graph", str(node_id), "malformed", owner_scope)
            )
            continue
        ordinal = ordinals.get(asset_id, 0)
        ordinals[asset_id] = ordinal + 1
        try:
            candidates.append(
                _ResolvedCandidate(
                    authority="depth_graph",
                    asset_id=asset_id,
                    canonical_id=str(node_id),
                    kind=cast(ContentKind, str(node_type)),
                    text=str(text),
                    ordinal=ordinal,
                    created_at=str(created_at) if created_at is not None else None,
                    source_event_ids=twin.source_event_ids,
                )
            )
        except ValueError:
            exclusions.append(
                _opaque_exclusion("depth_graph", str(node_id), "malformed", owner_scope)
            )
    return candidates, tuple(exclusions)


def resolve_artifact_note_candidates(
    *,
    owner_user_id: str,
    artifact_ids: Sequence[str],
    artifact_store: FilesystemArtifactStore,
    max_candidates: int = MAX_CANDIDATES,
) -> tuple[list[_ResolvedCandidate], tuple[ExclusionReceipt, ...]]:
    if len(artifact_ids) > MAX_REQUEST_ITEMS:
        raise ValueError("too many artifact ids")
    candidates: list[_ResolvedCandidate] = []
    exclusions: list[ExclusionReceipt] = []
    owner_scope = account_scope_digest(owner_user_id)
    consumed_bytes = 0
    for raw_artifact_id in dict.fromkeys(artifact_ids):
        if not _valid_request_id(raw_artifact_id):
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", repr(raw_artifact_id), "malformed", owner_scope
                )
            )
            continue
        assert isinstance(raw_artifact_id, str)
        artifact_id = raw_artifact_id.strip()
        if len(candidates) >= max_candidates:
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", artifact_id, "aggregate_budget", owner_scope
                )
            )
            continue
        try:
            authority = ArtifactAuthority(owner_user_id, artifact_id)
        except ValueError:
            exclusions.append(
                _opaque_exclusion("artifact_note", artifact_id, "malformed", owner_scope)
            )
            continue
        remaining_bytes = MAX_AGGREGATE_ARTIFACT_HTML_BYTES - consumed_bytes
        if remaining_bytes < 1:
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", artifact_id, "aggregate_budget", owner_scope
                )
            )
            continue
        try:
            html = artifact_store.read_bounded_if_present(
                authority,
                max_bytes=min(MAX_ARTIFACT_HTML_BYTES, remaining_bytes),
            )
        except (OSError, UnicodeDecodeError, UnsafeArtifactState):
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", artifact_id, "resolver_unavailable", owner_scope
                )
            )
            continue
        if html is None:
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", artifact_id, "missing_asset", owner_scope
                )
            )
            continue
        consumed_bytes += len(html.encode("utf-8"))
        # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
        try:
            body = parse_body_from_html(html)
        except (ValueError, json.JSONDecodeError):
            # fmt: on
            exclusions.append(
                _opaque_exclusion("artifact_note", artifact_id, "malformed", owner_scope)
            )
            continue
        if body.investigation_id != artifact_id:
            exclusions.append(
                _opaque_exclusion("artifact_note", artifact_id, "malformed", owner_scope)
            )
            continue
        if len(body.source_event_ids) > 32:
            exclusions.append(
                _opaque_exclusion(
                    "artifact_note", artifact_id, "aggregate_budget", owner_scope
                )
            )
            continue
        found_note = False
        for ordinal, note in enumerate(body.agent_notes):
            text = note.strip() if isinstance(note, str) else ""
            if not text:
                continue
            found_note = True
            if len(candidates) >= max_candidates:
                exclusions.append(
                    _opaque_exclusion(
                        "artifact_note", artifact_id, "aggregate_budget", owner_scope
                    )
                )
                break
            canonical_id = hashlib.sha256(
                f"artifact-note-v1\0{artifact_id}\0{ordinal}\0{hashlib.sha256(text.encode()).hexdigest()}".encode()
            ).hexdigest()
            try:
                candidates.append(
                    _ResolvedCandidate(
                        authority="artifact_note",
                        asset_id=artifact_id,
                        canonical_id=canonical_id,
                        kind="artifact_note",
                        text=text,
                        ordinal=ordinal,
                        created_at=None,
                        source_event_ids=tuple(body.source_event_ids),
                    )
                )
            except ValueError:
                exclusions.append(
                    _opaque_exclusion(
                        "artifact_note",
                        f"{artifact_id}:{ordinal}",
                        "malformed",
                        owner_scope,
                    )
                )
        if not found_note:
            exclusions.append(
                _opaque_exclusion("artifact_note", artifact_id, "no_content", owner_scope)
            )
    return candidates, tuple(exclusions)


def build_canonical_recursive_pack(
    *,
    store: EngagementStore,
    owner_user_id: str,
    asset_ids: Sequence[str],
    asset_owner: OwnerResolver,
    goal: str,
    con: Any = None,
    explicit_note_ids: Sequence[str] = (),
    artifact_ids: Sequence[str] = (),
    artifact_store: FilesystemArtifactStore | None = None,
    caller_advisory_text: Sequence[str] = (),
    token_budget: int = 2048,
    max_unit_bytes: int = 4096,
    max_units: int = 32,
    per_asset_limit: int = 8,
) -> RecursiveNotesPack:
    twin_candidates, twin_exclusions = resolve_twin_candidates(
        store=store,
        owner_user_id=owner_user_id,
        asset_ids=asset_ids,
        asset_owner=asset_owner,
        explicit_note_ids=explicit_note_ids,
    )
    graph_candidates: list[_ResolvedCandidate] = []
    graph_exclusions: tuple[ExclusionReceipt, ...] = ()
    if con is not None:
        graph_candidates, graph_exclusions = resolve_graph_candidates(
            con=con,
            store=store,
            owner_user_id=owner_user_id,
            asset_ids=asset_ids,
            asset_owner=asset_owner,
        )
    artifact_candidates: list[_ResolvedCandidate] = []
    artifact_exclusions: tuple[ExclusionReceipt, ...] = ()
    if artifact_ids:
        artifact_candidates, artifact_exclusions = resolve_artifact_note_candidates(
            owner_user_id=owner_user_id,
            artifact_ids=artifact_ids,
            artifact_store=artifact_store or FilesystemArtifactStore(),
            max_candidates=max(
                0, MAX_CANDIDATES - len(twin_candidates) - len(graph_candidates)
            ),
        )
    if len(caller_advisory_text) > MAX_ADVISORY_ITEMS:
        raise ValueError("too many caller advisory items")
    if any(
        isinstance(text, str) and len(text.encode("utf-8")) > MAX_ADVISORY_BYTES
        for text in caller_advisory_text
    ):
        raise ValueError("caller advisory item is too large")
    advisory_exclusions = tuple(
        _opaque_exclusion(
            "caller_supplied_advisory",
            text if isinstance(text, str) else repr(text),
            "caller_supplied_advisory" if isinstance(text, str) else "malformed",
            account_scope_digest(owner_user_id),
        )
        for text in caller_advisory_text
        if not isinstance(text, str) or text.strip()
    )
    pack = _assemble_resolved_notes_pack(
        twin_candidates + graph_candidates + artifact_candidates,
        owner_user_id=owner_user_id,
        goal=goal,
        token_budget=token_budget,
        max_unit_bytes=max_unit_bytes,
        max_units=max_units,
        per_asset_limit=per_asset_limit,
        prior_exclusions=(
            twin_exclusions + graph_exclusions + artifact_exclusions + advisory_exclusions
        ),
    )
    advisory_previews: list[AdvisoryPreview] = []
    advisory_tokens = 0
    remaining_tokens = pack.token_budget - pack.token_estimate
    for index, text in enumerate(caller_advisory_text):
        if not isinstance(text, str) or not text.strip():
            continue
        normalized = " ".join(text.split())
        tokens = max(1, (len(normalized.encode("utf-8")) + 3) // 4)
        if advisory_tokens + tokens > remaining_tokens:
            continue
        advisory_previews.append(
            AdvisoryPreview(
                unit_id=hashlib.sha256(f"caller-advisory-v1\0{index}\0{text}".encode()).hexdigest(),
                authority="caller_supplied_advisory",
                text=normalized,
                text_digest=digest_text(normalized),
                token_estimate=tokens,
            )
        )
        advisory_tokens += tokens
    return RecursiveNotesPack(
        units=pack.units,
        exclusions=pack.exclusions,
        token_estimate=pack.token_estimate,
        token_budget=pack.token_budget,
        candidate_count=pack.candidate_count,
        advisory_previews=tuple(advisory_previews),
        advisory_token_estimate=advisory_tokens,
    )
