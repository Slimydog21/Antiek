"""Immutable owner-qualified manifests and inert private HTML interview drafts."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection

from .authority import InterviewAccountAuthority
from .claims import CanonicalClaim, list_claims
from .consent import consent_state
from .contributor import get_active_attribution


class CompositionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CompositionDraft:
    draft_id: str
    project_id: str
    title: str
    manifest: dict[str, Any]
    manifest_sha256: str
    body_html: str
    body_sha256: str
    visibility: str


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _draft_id(authority: InterviewAccountAuthority, project_id: str, command_id: str) -> str:
    digest = _sha(f"antiek-interview-draft-v1\0{authority.account_digest}\0{project_id}\0{command_id}")
    return f"ivdr-{digest[:32]}"


def _claim_manifest(con: Any, authority: InterviewAccountAuthority, claim: CanonicalClaim) -> dict:
    cluster = con.execute(
        "SELECT m.cluster_id, m.stance, c.label, c.independent_attesters "
        "FROM interview_corroboration_members_authority m "
        "JOIN interview_corroboration_clusters_authority c "
        "ON c.account_digest = m.account_digest AND c.cluster_id = m.cluster_id "
        "WHERE m.account_digest = ? AND m.claim_id = ?",
        [authority.account_digest, claim.claim_id],
    ).fetchone()
    custody = con.execute(
        "SELECT cl.source_receipt_id, a.account_digest, a.investigation_digest, "
        "a.receipt_fingerprint, a.content_sha256, "
        "s.state_sha256, s.seal_fingerprint, m.manifest_sha256, m.seal_fingerprint "
        "FROM interview_claims_authority cl JOIN legal_document_admissions a "
        "ON a.receipt_id = cl.source_receipt_id AND a.document_id = cl.source_document_id "
        "JOIN legal_document_custody_seals s "
        "ON s.document_id = cl.source_document_id AND s.receipt_id = cl.source_receipt_id "
        "JOIN legal_chunk_manifest_seals m ON m.document_id = cl.source_document_id "
        "AND m.receipt_id = cl.source_receipt_id WHERE cl.account_digest = ? "
        "AND cl.owner_user_id = ? AND cl.claim_id = ?",
        [authority.account_digest, authority.account_id, claim.claim_id],
    ).fetchone()
    if custody is None:
        raise CompositionConflict("claim custody evidence is missing")
    required_scopes = {"record", "attribute"} if (
        claim.about_subject or claim.subject_ref is not None
    ) else {"record"}
    consent_rows = con.execute(
        "SELECT event_id, scope, granted, actor_kind, policy_version, recorded_at FROM ("
        "SELECT event_id, scope, granted, actor_kind, policy_version, recorded_at, "
        "row_number() OVER (PARTITION BY scope ORDER BY recorded_at DESC, event_id DESC) ordinal "
        "FROM interview_consent_events WHERE account_digest = ? AND owner_user_id = ? "
        "AND interview_id = ?) ranked WHERE ordinal = 1 ORDER BY scope",
        [authority.account_digest, authority.account_id, claim.interview_id],
    ).fetchall()
    consent_evidence = [
        {
            "event_id": str(row[0]), "scope": str(row[1]), "granted": bool(row[2]),
            "actor_kind": str(row[3]), "policy_version": int(row[4]),
            "recorded_at": str(row[5]),
        }
        for row in consent_rows if str(row[1]) in required_scopes
    ]
    if {event["scope"] for event in consent_evidence if event["granted"]} != required_scopes:
        raise CompositionConflict("current consent evidence is incomplete")
    contributor = get_active_attribution(
        con, authority, project_id=claim.project_id, interview_id=claim.interview_id
    )
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "interview_id": claim.interview_id,
        "question_id": claim.question_id,
        "source_document_id": claim.source_document_id,
        "about_subject": claim.about_subject,
        "is_third_party": claim.is_third_party,
        "subject_ref": claim.subject_ref,
        "verification": claim.verification,
        "confidence": claim.confidence,
        "custody": {
            "source_receipt_id": str(custody[0]),
            "legal_account_digest": str(custody[1]),
            "investigation_digest": str(custody[2]),
            "receipt_fingerprint": str(custody[3]),
            "source_content_sha256": str(custody[4]),
            "document_state_sha256": str(custody[5]),
            "document_seal_fingerprint": str(custody[6]),
            "chunk_manifest_sha256": str(custody[7]),
            "chunk_seal_fingerprint": str(custody[8]),
        },
        "consent_evidence": consent_evidence,
        "contributor": None if contributor is None else {
            "event_id": contributor.event_id,
            "contributor_ref": contributor.contributor_ref,
            "display_label": contributor.display_label,
            "evidence_basis": contributor.evidence_basis,
            "evidence_ref": contributor.evidence_ref,
            "consent_event_ids": list(contributor.consent_event_ids),
            "active_at_composition": contributor.active,
        },
        "corroboration": None if cluster is None else {
            "cluster_id": str(cluster[0]), "stance": str(cluster[1]),
            "label": str(cluster[2]), "independent_attesters": int(cluster[3]),
        },
    }


def _verification_label(claim: dict) -> str:
    labels = {
        "multiply_attested": "Multiply attested",
        "operator_attested": "Operator attested",
        "contradicted": "Disputed",
        "unverified": "Unverified interview claim",
    }
    value = claim.get("verification")
    if value not in labels:
        raise CompositionConflict(f"unknown claim verification: {value!r}")
    return labels[value]


def _render_html(*, draft_id: str, title: str, claims: list[dict]) -> str:
    sections: list[str] = []
    for claim in claims:
        label = _verification_label(claim)
        subject = claim["subject_ref"] or "not attributed to an identified subject"
        corroboration = claim["corroboration"]
        corroboration_text = (
            "No corroboration cluster frozen."
            if corroboration is None
            else "Corroboration cluster " + html.escape(corroboration["cluster_id"])
            + ": " + html.escape(corroboration["label"])
            + ", stance " + html.escape(corroboration["stance"])
            + ", independent attesters " + str(corroboration["independent_attesters"]) + "."
        )
        consent_ids = ", ".join(
            html.escape(event["scope"] + ":" + event["event_id"])
            for event in claim["consent_evidence"]
        )
        contributor = claim["contributor"]
        contributor_text = (
            "No contributor credit frozen."
            if contributor is None
            else "Contributor credit " + html.escape(contributor["display_label"])
            + " (" + html.escape(contributor["contributor_ref"])
            + "), attribution event " + html.escape(contributor["event_id"])
            + ", basis " + html.escape(contributor["evidence_basis"]) + "."
        )
        sections.append(
            '<section class="antiek-claim" data-claim-id="'
            + html.escape(claim["claim_id"], quote=True)
            + '"><p class="claim-text">'
            + html.escape(claim["text"])
            + '</p><aside class="claim-evidence" aria-label="Claim evidence"><strong>'
            + html.escape(label)
            + "</strong><span> Source interview "
            + html.escape(claim["interview_id"])
            + ", answer document "
            + html.escape(claim["source_document_id"])
            + ", subject "
            + html.escape(subject)
            + ".</span><span> Claim " + html.escape(claim["claim_id"])
            + ", question " + html.escape(claim["question_id"])
            + ", admission receipt " + html.escape(claim["custody"]["source_receipt_id"])
            + ".</span><span> " + corroboration_text
            + "</span><span> Consent evidence " + consent_ids
            + ".</span><span> " + contributor_text + "</span></aside></section>"
        )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>" + html.escape(title) + "</title></head><body>"
        '<article data-antiek-document-kind="interview-composition" data-draft-id="'
        + html.escape(draft_id, quote=True) + '"><header><h1>' + html.escape(title)
        + "</h1><p>Private evidence draft. Verification labels and source references are "
        "part of this artifact.</p></header>" + "".join(sections) + "</article></body></html>"
    )


def _from_row(row: tuple[Any, ...]) -> CompositionDraft:
    manifest = json.loads(str(row[3]))
    return CompositionDraft(
        draft_id=str(row[0]), project_id=str(row[1]), title=str(row[2]),
        manifest=manifest, manifest_sha256=str(row[4]), body_html=str(row[5]),
        body_sha256=str(row[6]), visibility=str(row[7]),
    )


def _require_manifest_consent(
    con: Any, authority: InterviewAccountAuthority, manifest: dict[str, Any]
) -> None:
    for claim in manifest.get("claims", []):
        custody = con.execute(
            "SELECT a.receipt_fingerprint, a.content_sha256, s.state_sha256, "
            "s.seal_fingerprint, m.manifest_sha256, m.seal_fingerprint "
            "FROM legal_document_admissions a JOIN legal_document_custody_seals s "
            "ON s.document_id = a.document_id AND s.receipt_id = a.receipt_id "
            "JOIN legal_chunk_manifest_seals m ON m.document_id = a.document_id "
            "AND m.receipt_id = a.receipt_id WHERE a.account_digest = ? "
            "AND a.investigation_digest = ? AND a.receipt_id = ? AND a.document_id = ?",
            [claim["custody"]["legal_account_digest"],
             claim["custody"]["investigation_digest"],
             claim["custody"]["source_receipt_id"],
             claim["source_document_id"]],
        ).fetchone()
        expected_custody = claim["custody"]
        if custody is None or tuple(str(value) for value in custody) != (
            expected_custody["receipt_fingerprint"],
            expected_custody["source_content_sha256"],
            expected_custody["document_state_sha256"],
            expected_custody["document_seal_fingerprint"],
            expected_custody["chunk_manifest_sha256"],
            expected_custody["chunk_seal_fingerprint"],
        ):
            raise CompositionConflict("composition custody evidence no longer matches")
        for event in claim["consent_evidence"]:
            frozen = con.execute(
                "SELECT scope, granted, actor_kind, policy_version, recorded_at "
                "FROM interview_consent_events WHERE account_digest = ? AND owner_user_id = ? "
                "AND interview_id = ? AND event_id = ?",
                [authority.account_digest, authority.account_id, claim["interview_id"],
                 event["event_id"]],
            ).fetchone()
            if frozen is None or (
                str(frozen[0]), bool(frozen[1]), str(frozen[2]), int(frozen[3]), str(frozen[4])
            ) != (
                event["scope"], event["granted"], event["actor_kind"],
                event["policy_version"], event["recorded_at"],
            ):
                raise CompositionConflict("composition consent evidence no longer matches")
        contributor = claim.get("contributor")
        if contributor is not None:
            frozen_credit = con.execute(
                "SELECT contributor_ref, display_label, evidence_basis, evidence_ref, "
                "consent_event_ids_json FROM interview_contributor_attribution_events "
                "WHERE account_digest = ? AND owner_user_id = ? AND project_id = ? "
                "AND interview_id = ? AND event_id = ? AND action = 'bind'",
                [authority.account_digest, authority.account_id, manifest["project_id"],
                 claim["interview_id"], contributor["event_id"]],
            ).fetchone()
            if frozen_credit is None or (
                str(frozen_credit[0]), str(frozen_credit[1]), str(frozen_credit[2]),
                str(frozen_credit[3]), tuple(json.loads(str(frozen_credit[4]))),
            ) != (
                contributor["contributor_ref"], contributor["display_label"],
                contributor["evidence_basis"], contributor["evidence_ref"],
                tuple(contributor["consent_event_ids"]),
            ):
                raise CompositionConflict("composition contributor evidence no longer matches")
        scopes = consent_state(con, authority, interview_id=str(claim["interview_id"]))
        if "record" not in scopes:
            raise CompositionConflict("record consent is not currently granted")
        if (
            claim["about_subject"]
            or claim["subject_ref"] is not None
            or contributor is not None
        ) and "attribute" not in scopes:
            raise CompositionConflict("attribute consent is not currently granted")


def create_private_draft(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    command_id: str,
    title: str,
    claim_ids: list[str],
) -> CompositionDraft:
    if not isinstance(con, LockedConnection):
        raise TypeError("canonical composition requires a LockedConnection")
    if not command_id or command_id != command_id.strip():
        raise ValueError("composition command_id is invalid")
    if not title or title != title.strip():
        raise ValueError("composition title is invalid")
    if not claim_ids or len(set(claim_ids)) != len(claim_ids):
        raise ValueError("composition claim_ids must be non-empty and unique")
    project = con.execute(
        "SELECT title FROM interview_projects_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND project_id = ?",
        [authority.account_digest, authority.account_id, project_id],
    ).fetchone()
    if project is None:
        raise ValueError("interview project not found")
    request_json = _canonical_json({
        "schema_version": 1, "project_id": project_id, "title": title,
        "claim_ids": claim_ids,
    })
    request_sha = _sha(request_json)
    existing = con.execute(
        "SELECT draft_id, project_id, title, manifest_json, manifest_sha256, body_html, "
        "body_sha256, visibility, request_sha256 FROM interview_composition_drafts_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND command_id = ?",
        [authority.account_digest, authority.account_id, command_id],
    ).fetchone()
    if existing is not None:
        if str(existing[8]) != request_sha:
            raise CompositionConflict("composition command was reused with different input")
        draft = _from_row(tuple(existing[:8]))
        if _sha(_canonical_json(draft.manifest)) != draft.manifest_sha256:
            raise CompositionConflict("composition manifest integrity check failed")
        if _sha(draft.body_html) != draft.body_sha256:
            raise CompositionConflict("composition HTML integrity check failed")
        _require_manifest_consent(con, authority, draft.manifest)
        return draft
    visible = {claim.claim_id: claim for claim in list_claims(con, authority, project_id=project_id)}
    if any(claim_id not in visible for claim_id in claim_ids):
        raise ValueError("one or more consent-current project claims were not found")
    claims = [_claim_manifest(con, authority, visible[claim_id]) for claim_id in claim_ids]
    manifest = {
        "schema_version": 1, "project_id": project_id, "project_title": str(project[0]),
        "title": title, "claims": claims,
    }
    manifest_json = _canonical_json(manifest)
    manifest_sha = _sha(manifest_json)
    draft_id = _draft_id(authority, project_id, command_id)
    body_html = _render_html(draft_id=draft_id, title=title, claims=claims)
    body_sha = _sha(body_html)
    owns_transaction = not con.transaction_active
    if owns_transaction:
        con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO interview_composition_drafts_authority "
            "(account_digest, draft_id, project_id, owner_user_id, command_id, request_sha256, "
            "title, manifest_json, manifest_sha256, body_html, body_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [authority.account_digest, draft_id, project_id, authority.account_id, command_id,
             request_sha, title, manifest_json, manifest_sha, body_html, body_sha],
        )
        if owns_transaction:
            con.execute("COMMIT")
    except BaseException:
        if owns_transaction:
            con.execute("ROLLBACK")
        raise
    return get_private_draft(con, authority, draft_id=draft_id)


def get_private_draft(
    con: Any, authority: InterviewAccountAuthority, *, draft_id: str
) -> CompositionDraft:
    row = con.execute(
        "SELECT draft_id, project_id, title, manifest_json, manifest_sha256, body_html, "
        "body_sha256, visibility FROM interview_composition_drafts_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND draft_id = ?",
        [authority.account_digest, authority.account_id, draft_id],
    ).fetchone()
    if row is None:
        raise ValueError("private composition draft not found")
    draft = _from_row(tuple(row))
    if _sha(_canonical_json(draft.manifest)) != draft.manifest_sha256:
        raise CompositionConflict("composition manifest integrity check failed")
    if _sha(draft.body_html) != draft.body_sha256:
        raise CompositionConflict("composition HTML integrity check failed")
    _require_manifest_consent(con, authority, draft.manifest)
    return draft


__all__ = [
    "CompositionConflict", "CompositionDraft", "create_private_draft", "get_private_draft",
]
