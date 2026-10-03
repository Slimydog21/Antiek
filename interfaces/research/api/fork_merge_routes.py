"""Fork-merge routes (thread-merge + document fork SPR-02).

The selective thread-outcome merge INTO A FORK — the shipped source-merge
shape (preview → receipt → commit) retargeted, its own route family. NOTHING
hangs off ``/research/artifacts/compose`` (whose API layer is
default-mutating on main — the spec's hard boundary), and the retired
in-place ``/research/artifacts/source-merge/preview|apply|commit`` routes
stay retired and unedited; only restore lives there, untouched.

  POST /research/artifacts/fork-merge/preview — no writes. The receipt:
      the merge id binding (fork + selection + detected conflicts), the
      items resolved against the live distill read, the conflict list on
      the three-source honest ladder (cross-member pairs / anchor passages
      / operator flags), before/after hashes (after = every item landing).
  POST /research/artifacts/fork-merge/commit — the multi-ack discipline
      carried: acknowledge_fork_document_mutation required always,
      acknowledge_conflicts required when the preview listed any; the
      commit binds to the preview (merge id + before-hash — a stale or
      edited selection is a 409); EVERY conflicted item needs a resolution
      (accept | keep_fork | skip) or the refusal is atomic (409, no partial
      write). Each resolution writes its audit row in the same scope.

Owner-scoped on the unit conventions (_reader_owner_id, _resolve_db_path).
Never auto-resolves. Items merge their own text only — what the operator
lawfully sees in the artifact; no source body is read on this path.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.research_artifact.fork_merge import (
    ForkMergeBodyUnavailableError,
    ForkMergeCommitReceipt,
    ForkMergeItemError,
    ForkMergePreviewReceipt,
    ForkMergeUnresolvedConflictsError,
    Resolution,
    commit_fork_merge,
    preview_fork_merge,
)


class MergeItemIn(BaseModel):
    """One selected outcome item — DistilledNode identity."""

    investigation_id: str = Field(min_length=1, max_length=200)
    node_id: str = Field(min_length=1, max_length=200)


class MergePreviewIn(BaseModel):
    fork_id: str = Field(min_length=1, max_length=200)
    items: list[MergeItemIn] = Field(min_length=1, max_length=100)
    """Operator-flagged conflicts (ladder source c): selected items the
    operator names as conflicted."""
    flagged_conflicts: list[MergeItemIn] = Field(default_factory=list, max_length=100)


class ResolutionIn(BaseModel):
    investigation_id: str = Field(min_length=1, max_length=200)
    node_id: str = Field(min_length=1, max_length=200)
    choice: str = Field(pattern="^(accept|keep_fork|skip)$")


class MergeCommitIn(MergePreviewIn):
    """The commit binds to the reviewed preview and carries the acks."""

    expected_merge_id: str = Field(min_length=1, max_length=200)
    expected_before_fork_hash: str = Field(min_length=64, max_length=64)
    resolutions: list[ResolutionIn] = Field(default_factory=list, max_length=100)
    acknowledge_fork_document_mutation: bool = False
    acknowledge_conflicts: bool = False
    operator_reviewer: str | None = Field(default=None, max_length=160)


class MergeItemOut(BaseModel):
    investigation_id: str
    node_id: str
    kind: str
    text: str
    text_sha256: str
    source_document_id: str | None


class MergeConflictOut(BaseModel):
    conflict_id: str
    kind: str
    item_refs: list[list[str]]
    detail: str
    anchor_id: str | None


class MergePreviewOut(BaseModel):
    status: str
    merge_id: str
    fork_id: str
    fork_document_id: str
    items: list[MergeItemOut]
    conflicts: list[MergeConflictOut]
    before_fork_hash: str
    after_fork_hash: str
    fork_bytes_before: int
    fork_bytes_after: int
    writes_performed: bool


class MergeCommitOut(MergePreviewOut):
    commit_id: str
    event_id: str | None
    resolutions: dict[str, str]


def _preview_out(
    receipt: ForkMergePreviewReceipt | ForkMergeCommitReceipt,
) -> MergePreviewOut:
    return MergePreviewOut(
        status=receipt.status,
        merge_id=receipt.merge_id,
        fork_id=receipt.fork_id,
        fork_document_id=receipt.fork_document_id,
        items=[
            MergeItemOut(
                investigation_id=i.investigation_id,
                node_id=i.node_id,
                kind=i.kind,
                text=i.text,
                text_sha256=i.text_sha256,
                source_document_id=i.source_document_id,
            )
            for i in receipt.items
        ],
        conflicts=[
            MergeConflictOut(
                conflict_id=c.conflict_id,
                kind=c.kind,
                item_refs=[list(ref) for ref in c.item_refs],
                detail=c.detail,
                anchor_id=c.anchor_id,
            )
            for c in receipt.conflicts
        ],
        before_fork_hash=receipt.before_fork_hash,
        after_fork_hash=receipt.after_fork_hash,
        fork_bytes_before=receipt.fork_bytes_before,
        fork_bytes_after=receipt.fork_bytes_after,
        writes_performed=receipt.writes_performed,
    )


def _refs(items: list[MergeItemIn]) -> list[tuple[str, str]]:
    return [(i.investigation_id, i.node_id) for i in items]


def register_fork_merge_routes(app: FastAPI) -> None:
    """Mount the fork-merge routes. One call from create_app, beside
    register_fork_routes."""

    @app.post(
        "/research/artifacts/fork-merge/preview",
        response_model=MergePreviewOut,
        tags=["research-artifacts", "fork-merge"],
    )
    def fork_merge_preview(body: MergePreviewIn, request: Request) -> MergePreviewOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            receipt = preview_fork_merge(
                con,
                owner_user_id=owner,
                fork_id=body.fork_id,
                item_refs=_refs(body.items),
                flagged=_refs(body.flagged_conflicts),
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="fork_not_found") from None
        except ForkMergeBodyUnavailableError as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from refused
        except ForkMergeItemError as unknown:
            raise HTTPException(status_code=422, detail=str(unknown)) from unknown
        finally:
            con.close()
        return _preview_out(receipt)

    @app.post(
        "/research/artifacts/fork-merge/commit",
        response_model=MergeCommitOut,
        tags=["research-artifacts", "fork-merge"],
    )
    def fork_merge_commit(body: MergeCommitIn, request: Request) -> MergeCommitOut:
        from runtime.db_lock import connect_write

        owner = _reader_owner_id(request)
        # The multi-ack discipline, retargeted: the operator acknowledges the
        # fork body rewrite ALWAYS, and the conflict list when there is one.
        if not body.acknowledge_fork_document_mutation:
            raise HTTPException(
                status_code=409,
                detail="fork_merge_acknowledgement_required: set "
                "acknowledge_fork_document_mutation to commit a merge that "
                "rewrites the fork's body",
            )
        db = _resolve_db_path()
        with connect_write(db, purpose="research_artifact/fork_merge_commit") as con:
            try:
                # The conflict-acknowledgement gate keys on the REAL preview,
                # not the client's say-so: recompute cheaply before the ack
                # check so an empty-conflict merge never demands a false ack.
                preview = preview_fork_merge(
                    con,
                    owner_user_id=owner,
                    fork_id=body.fork_id,
                    item_refs=_refs(body.items),
                    flagged=_refs(body.flagged_conflicts),
                )
                if preview.conflicts and not body.acknowledge_conflicts:
                    raise HTTPException(
                        status_code=409,
                        detail="fork_merge_conflicts_acknowledgement_required: "
                        "the preview lists conflicts — acknowledge them and "
                        "resolve every conflicted item",
                    )
                receipt = commit_fork_merge(
                    con,
                    owner_user_id=owner,
                    fork_id=body.fork_id,
                    item_refs=_refs(body.items),
                    flagged=_refs(body.flagged_conflicts),
                    resolutions=[
                        Resolution(
                            investigation_id=r.investigation_id,
                            node_id=r.node_id,
                            choice=r.choice,
                        )
                        for r in body.resolutions
                    ],
                    expected_merge_id=body.expected_merge_id,
                    expected_before_fork_hash=body.expected_before_fork_hash,
                    operator_reviewer=body.operator_reviewer,
                )
            except KeyError:
                raise HTTPException(
                    status_code=404, detail="fork_not_found"
                ) from None
            except ForkMergeBodyUnavailableError as refused:
                raise HTTPException(
                    status_code=409, detail=str(refused)
                ) from refused
            except ForkMergeUnresolvedConflictsError as unresolved:
                raise HTTPException(
                    status_code=409, detail=str(unresolved)
                ) from unresolved
            except ForkMergeItemError as unknown:
                raise HTTPException(
                    status_code=422, detail=str(unknown)
                ) from unknown
            except ValueError as refused:
                detail = str(refused)
                status = (
                    409
                    if detail.startswith(
                        ("fork_merge_preview_binding_mismatch", "fork_merge_stale")
                    )
                    else 422
                )
                raise HTTPException(status_code=status, detail=detail) from refused
        out = _preview_out(receipt)
        return MergeCommitOut(
            **out.model_dump(),
            commit_id=receipt.commit_id,
            event_id=receipt.event_id,
            resolutions=receipt.resolutions,
        )


__all__ = ["register_fork_merge_routes"]
