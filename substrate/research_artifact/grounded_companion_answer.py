"""Closed grounded-answer artifact for derived companion turns."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Any, Final, Protocol

SCHEMA_VERSION: Final = "antiek.derived-companion-answer.v1"
MAX_CLAIMS: Final = 64
MAX_CLAIM_BYTES: Final = 8 * 1024
MAX_ANSWER_BYTES: Final = 128 * 1024
_RECEIPT_ID = re.compile(r"rex_[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{64}")


class GroundedAnswerError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnswerClaimInput:
    text: str
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundedAnswerCandidate:
    claims: tuple[AnswerClaimInput, ...]


@dataclass(frozen=True)
class AnswerAdmissionExpectation:
    turn_id: str
    evidence_pack_sha256: str
    output_digest: str


@dataclass(frozen=True)
class VerifiedCompanionExecutionReceipt:
    receipt_id: str
    receipt_digest: str
    status: str
    provider: str
    model: str
    turn_id: str
    evidence_pack_sha256: str
    output_digest: str


class CompanionExecutionReceiptVerifier(Protocol):
    def __call__(
        self, expectation: AnswerAdmissionExpectation
    ) -> VerifiedCompanionExecutionReceipt: ...


def candidate_digest(candidate: GroundedAnswerCandidate) -> str:
    return _sha(_json(_candidate_payload(candidate)))


def build_grounded_answer(
    *,
    turn_id: str,
    evidence_pack: dict[str, Any],
    candidate: GroundedAnswerCandidate,
    receipt: VerifiedCompanionExecutionReceipt,
) -> dict[str, Any]:
    payload = _candidate_payload(candidate)
    output_digest = _sha(_json(payload))
    pack_sha = str(evidence_pack.get("pack_sha256", ""))
    _validate_receipt(receipt, turn_id=turn_id, pack_sha=pack_sha,
                      output_digest=output_digest)
    citations = evidence_pack.get("citations")
    if not isinstance(citations, list):
        raise GroundedAnswerError("evidence pack citations are invalid")
    citation_map: dict[str, dict[str, Any]] = {}
    for citation in citations:
        if not isinstance(citation, dict):
            raise GroundedAnswerError("evidence pack citation is invalid")
        citation_id = citation.get("citation_id")
        if not isinstance(citation_id, str) or citation_id in citation_map:
            raise GroundedAnswerError("evidence pack citation identity is invalid")
        citation_map[citation_id] = citation

    claims: list[dict[str, Any]] = []
    cited_ids: list[str] = []
    html_claims: list[str] = []
    answer_id = "dans_" + _sha(f"{turn_id}\0{receipt.receipt_id}\0{output_digest}")
    for ordinal, raw in enumerate(payload["claims"]):
        claim_citations = raw["citation_ids"]
        if len(claim_citations) != len(set(claim_citations)):
            raise GroundedAnswerError("claim repeats a citation")
        unknown = [item for item in claim_citations if item not in citation_map]
        if unknown:
            raise GroundedAnswerError("claim cites evidence outside the admitted pack")
        claim_id = "dclaim_" + _sha(_json({
            "answer_id": answer_id, "ordinal": ordinal, "text": raw["text"],
            "citation_ids": claim_citations,
        }))
        supported = bool(claim_citations)
        claims.append({"claim_id": claim_id, "ordinal": ordinal, "text": raw["text"],
                       "citation_ids": claim_citations, "supported": supported})
        links = []
        for citation_id in claim_citations:
            if citation_id not in cited_ids:
                cited_ids.append(citation_id)
            citation = citation_map[citation_id]
            anchor = html.escape(str(citation.get("section_anchor", "")), quote=True)
            links.append(
                f'<a href="#{anchor}" data-citation-id="{html.escape(citation_id)}">'
                f'[{len(links) + 1}]</a>'
            )
        grounding = "supported" if supported else "unsupported"
        suffix = " " + " ".join(links) if links else ""
        html_claims.append(
            f'<p data-claim-id="{claim_id}" data-grounding="{grounding}">'
            f'{html.escape(raw["text"])}{suffix}</p>'
        )
    rendered = (
        f'<article data-answer-id="{answer_id}" data-schema-version="{SCHEMA_VERSION}">'
        + "".join(html_claims) + "</article>"
    )
    if len(rendered.encode("utf-8")) > MAX_ANSWER_BYTES:
        raise GroundedAnswerError("rendered answer exceeds the byte limit")
    claims_json = _json(claims)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "answer_id": answer_id,
        "turn_id": turn_id,
        "evidence_pack_sha256": pack_sha,
        "provider": receipt.provider,
        "model": receipt.model,
        "execution_receipt_id": receipt.receipt_id,
        "execution_receipt_digest": receipt.receipt_digest,
        "output_digest": output_digest,
        "claims": claims,
        "claims_sha256": _sha(claims_json),
        "cited_citation_ids": cited_ids,
        "unsupported_claim_count": sum(not claim["supported"] for claim in claims),
        "answer_html": rendered,
        "answer_html_sha256": _sha(rendered),
    }
    artifact["artifact_sha256"] = _sha(_json(artifact))
    return artifact


def public_grounded_answer(artifact: dict[str, Any]) -> dict[str, Any]:
    return {key: artifact[key] for key in (
        "schema_version", "answer_id", "evidence_pack_sha256", "provider", "model",
        "claims", "cited_citation_ids", "unsupported_claim_count", "answer_html",
        "answer_html_sha256", "artifact_sha256",
    )}


def _candidate_payload(candidate: GroundedAnswerCandidate) -> dict[str, Any]:
    if not isinstance(candidate, GroundedAnswerCandidate):
        raise GroundedAnswerError("answer candidate is invalid")
    if not 1 <= len(candidate.claims) <= MAX_CLAIMS:
        raise GroundedAnswerError("answer must contain a bounded claim set")
    claims = []
    for claim in candidate.claims:
        if not isinstance(claim, AnswerClaimInput):
            raise GroundedAnswerError("answer claim is invalid")
        text = claim.text.strip() if isinstance(claim.text, str) else ""
        if not text or len(text.encode("utf-8")) > MAX_CLAIM_BYTES:
            raise GroundedAnswerError("answer claim text is invalid")
        if not isinstance(claim.citation_ids, tuple) or not all(
            isinstance(item, str) and item for item in claim.citation_ids
        ):
            raise GroundedAnswerError("answer claim citations are invalid")
        claims.append({"text": text, "citation_ids": list(claim.citation_ids)})
    return {"schema_version": SCHEMA_VERSION, "claims": claims}


def _validate_receipt(
    receipt: VerifiedCompanionExecutionReceipt, *, turn_id: str, pack_sha: str,
    output_digest: str,
) -> None:
    if (not isinstance(receipt, VerifiedCompanionExecutionReceipt)
            or not _RECEIPT_ID.fullmatch(receipt.receipt_id)
            or not _SHA.fullmatch(receipt.receipt_digest)
            or receipt.status != "settled"
            or not receipt.provider.strip() or not receipt.model.strip()
            or receipt.turn_id != turn_id or receipt.evidence_pack_sha256 != pack_sha
            or receipt.output_digest != output_digest or not _SHA.fullmatch(pack_sha)):
        raise GroundedAnswerError("execution receipt does not bind the answer")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["AnswerAdmissionExpectation", "AnswerClaimInput",
           "CompanionExecutionReceiptVerifier", "GroundedAnswerCandidate",
           "GroundedAnswerError", "VerifiedCompanionExecutionReceipt",
           "build_grounded_answer", "candidate_digest", "public_grounded_answer"]
