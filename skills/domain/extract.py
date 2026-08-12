"""Phase 8 knowledge extraction orchestrator.

Verbatim port of Researchmaxx ``knowledge_extraction.extract_and_patch``
(Sprint 6 day 2-3). One entry point ties together:

  1. ``classify_domains`` — pure keyword match against question +
     thesis text. Empty match ⇒ skip Phase 8 (legitimate — not every
     synthesis needs to compound into a domain skill).
  2. ``extract_findings`` — per matched domain, render the extraction
     prompt and call the LLM. Failure here is per-domain; other
     matched domains still get attempted.
  3. ``patch_skill`` — apply extracted findings to the on-disk
     SKILL.md.

LLM call is **injectable**. Production wires
``substrate.dispatch.dispatch`` via ``default_llm_call``; tests pass a
stub. The injection point is the key migration improvement over the
upstream's ``call_openrouter`` hard dependency.

Two-tier JSON parse + one-shot repair-retry preserved from upstream
(default ON, gated by ``ANTIEK_KE_REPAIR_ENABLED`` env var) —
matches the parser discipline in ``roles/decomposer/parser.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from .extraction_prompt import make_extraction_prompt
from .keywords import classify_domains
from .patch import patch_skill


class LLMCall(Protocol):
    """Injection point for the extraction LLM call.

    ``__call__`` takes the system + user prompts and returns the
    model's raw response text. Production wires a closure around
    ``substrate.dispatch.dispatch`` with role="knowledge_extractor";
    tests pass a stub that returns canned text.

    Raises ``RuntimeError`` (or any subclass) on transport failure.
    The orchestrator catches and continues with the next domain.
    """

    def __call__(self, *, system: str, user: str) -> str: ...


def _ke_repair_enabled() -> bool:
    """Mirror of the upstream ``RESEARCHMAXX_KE_REPAIR_ENABLED`` gate.
    Default ON. Disable with ``ANTIEK_KE_REPAIR_ENABLED=0``."""
    val = os.environ.get("ANTIEK_KE_REPAIR_ENABLED", "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    return True


def _try_parse_json(
    raw: str,
) -> tuple[dict | None, json.JSONDecodeError | None]:
    """Strict JSON parse + brace-slice fallback. Returns
    ``(parsed_dict, None)`` on success; ``(None, error)`` on failure.

    The brace-slice fallback (find outermost ``{...}`` window and
    retry strict parse) recovers from prose-wrapped responses
    (``Here is the JSON: {...}``) — same recovery tier as upstream.
    The repair-retry path one level up handles structural malformations
    by re-querying the model with a corrective prefix.
    """
    raw = raw.strip()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e_direct:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1]), None
            except json.JSONDecodeError as e_sliced:
                return None, e_sliced
        return None, e_direct


def _repair_prefix(parse_err: json.JSONDecodeError | None) -> str:
    """Build the corrective prefix the one-shot retry prepends to the
    user prompt. Tells the model what broke + restates the schema
    contract verbatim — same approach as the upstream KE repair pass."""
    error_message = str(parse_err) if parse_err else "unknown JSON parse error"
    return (
        "## Repair retry (one-shot)\n"
        "Your previous response was not parseable JSON.\n"
        f"Parser error: {error_message}\n"
        "Re-emit the FULL JSON object only — no prose, no markdown fences, "
        "no commentary. Field names must match the schema exactly "
        "(\"text\", \"confidence\", \"date_observed\", \"source\")."
    )


def extract_findings(
    *,
    question: str,
    thesis: Any,
    domain: str,
    llm_call: LLMCall,
) -> dict | None:
    """Call the injected ``llm_call`` to extract findings for one
    domain. Returns the parsed dict (sections → finding lists) or
    ``None`` on transport / parse / retry-also-failed.

    The retry pass is paid only when the first parse fails AND repair
    is enabled. Mirrors the upstream's two-attempt cap exactly."""
    system_prompt, user_prompt = make_extraction_prompt(question, thesis, domain)

    try:
        first_call = cast(Any, llm_call).with_attempt(0) if getattr(llm_call, "with_attempt", None) else llm_call
        raw_first = first_call(system=system_prompt, user=user_prompt)
    except Exception as e:  # transport / API failure
        print(
            f"skills.domain.extract[{domain}]: LLM call failed: {e!r}",
            file=sys.stderr,
        )
        return None

    parsed, parse_err = _try_parse_json(raw_first)
    if parsed is not None:
        return parsed

    if not _ke_repair_enabled():
        print(
            f"skills.domain.extract[{domain}]: parse failed and repair "
            f"retry disabled: {parse_err!r}",
            file=sys.stderr,
        )
        return None

    # ── One-shot repair retry ──
    repair_user = _repair_prefix(parse_err) + "\n\n" + user_prompt
    try:
        repair_call = cast(Any, llm_call).with_attempt(1) if getattr(llm_call, "with_attempt", None) else llm_call
        raw_second = repair_call(system=system_prompt, user=repair_user)
    except Exception as e:
        print(
            f"skills.domain.extract[{domain}]: repair-retry transport "
            f"failed: {e!r}",
            file=sys.stderr,
        )
        return None

    parsed2, parse_err2 = _try_parse_json(raw_second)
    if parsed2 is not None:
        return parsed2

    print(
        f"skills.domain.extract[{domain}]: parse failed after one repair "
        f"retry: first={parse_err!r}; second={parse_err2!r}",
        file=sys.stderr,
    )
    return None


@dataclass
class ExtractionResult:
    """Phase 8 outcome. Surfaces to the Phase 8 verifier so it can
    decide whether the phase actually compounded (any domain
    patched ⇒ verify; empty ⇒ skip-verify legitimately)."""

    domains_matched: list[str] = field(default_factory=list)
    patched_skills: dict[str, list[str]] = field(default_factory=dict)
    findings_extracted: dict[str, dict] = field(default_factory=dict)

    @property
    def any_patched(self) -> bool:
        return any(self.patched_skills.values())

    def to_dict(self) -> dict:
        return {
            "domains_matched": list(self.domains_matched),
            "patched_skills": {k: list(v) for k, v in self.patched_skills.items()},
            "findings_extracted": dict(self.findings_extracted),
        }


def extract_and_patch(
    question: str,
    thesis: Any,
    investigation_id: str,
    *,
    llm_call: LLMCall | None = None,
    dry_run: bool = False,
    skills_root: Any | None = None,
) -> ExtractionResult:
    """Phase 8 entry point. Classify domains, extract findings via
    ``llm_call``, patch the matching SKILL.md files.

    ``dry_run`` classifies but does NOT extract or patch — useful for
    the operator CLI ``--dry-run`` flag and for Phase 8 readiness
    diagnostics.

    ``llm_call`` defaults to a substrate dispatch call when ``None``;
    tests inject a stub. The orchestrator never imports ``dispatch``
    directly — the LLM call site is the only seam to the substrate.
    """
    result = ExtractionResult()
    domains = classify_domains(question, thesis)
    result.domains_matched = domains

    if not domains:
        print(
            f"skills.domain.extract: no domains matched for {investigation_id}",
            file=sys.stderr,
        )
        return result

    if dry_run:
        print(
            f"skills.domain.extract: dry-run — would extract for {domains}",
            file=sys.stderr,
        )
        return result

    if llm_call is None:
        llm_call = default_llm_call_factory(investigation_id=investigation_id)

    for domain_index, domain in enumerate(domains):
        active_llm_call = llm_call
        if getattr(llm_call, "for_domain", None) is not None:
            active_llm_call = llm_call.for_domain(domain, domain_index)  # type: ignore[attr-defined]
        findings = extract_findings(
            question=question, thesis=thesis, domain=domain,
            llm_call=active_llm_call,
        )
        if findings is None:
            continue
        result.findings_extracted[domain] = findings
        patched = patch_skill(
            domain, findings,
            skills_root=skills_root,
        )
        if patched:
            result.patched_skills[domain] = patched

    return result


def default_llm_call_factory(*, investigation_id: str) -> LLMCall:
    """Build the production LLM-call closure: wraps
    ``substrate.dispatch.dispatch`` with role="knowledge_extractor".

    Lazy-imports ``substrate.dispatch`` so tests that inject their own
    ``llm_call`` don't pay the dispatch / config load cost.
    """
    from substrate.dispatch import dispatch

    class _OwnerAwareCall:
      def __init__(self, domain: str = "legacy", domain_index: int = 0, attempt: int = 0):
        self.domain = domain
        self.domain_index = domain_index
        self.attempt = attempt

      def for_domain(self, domain: str, domain_index: int) -> _OwnerAwareCall:
        return _OwnerAwareCall(domain, domain_index)

      def with_attempt(self, attempt: int) -> _OwnerAwareCall:
        return _OwnerAwareCall(self.domain, self.domain_index, attempt)

      def __call__(self, *, system: str, user: str) -> str:
        prompt = system + "\n\n" + user
        from interfaces.research.api.research_owner_dispatch import dispatch_loop_one
        domain_digest = hashlib.sha256(self.domain.encode()).hexdigest()[:16]
        result = dispatch_loop_one(
            prompt, "knowledge_extractor", investigation_id=investigation_id,
            semantic_call_id=f"phase8:{self.domain_index}:{domain_digest}", attempt=self.attempt,
        ) or dispatch(prompt, "knowledge_extractor", investigation_id=investigation_id)
        return result.text

    return _OwnerAwareCall()
