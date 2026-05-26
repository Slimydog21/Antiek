"""DRW SPR-03 M3 — the challenge resolver the living note drives.

``living_note.challenge_note`` takes a ``Resolver`` — ``(current_text,
challenge_text) -> refined_text | None``. ``None`` means "the graph can't
resolve this from what's known" and triggers the escalation seam. The
note-taker ships the *machinery*; the resolver is the one place that
decides, per challenge, whether a refinement is warranted.

Two honest distinctions this module makes that the bare ``Resolver`` type
cannot:

* **Resolved vs. unresolved.** The model is asked to refine the note in
  light of the challenge *only if the challenge is answerable from the
  note's own claim*; otherwise it returns nothing and we escalate. A
  refinement that merely restates the note is dropped (no-op), so a
  challenge never produces a cosmetic edit that looks like a change but
  isn't.

* **Unresolved vs. no-provider.** Without a configured model the call
  cannot run at all. That is NOT the same as "the graph can't resolve
  this" — escalating then would surface a misleading "needs more research"
  when the real state is "no model is configured". So a no-provider call
  raises :class:`ChallengeUnavailable`; the HTTP layer turns that into the
  honest no-key state (``AIActionFailure``), never a fabricated refinement
  and never a spurious escalation.

Determinism note (rigor #1): the *seq rule* that decides which refinement
wins lives in ``living_note.apply_refinement`` and is fully deterministic.
This resolver is the content source, not the ordering authority — it never
re-implements the seq check. A test injects a fixed function for the
content; the seq determinism is verified against the shipped rule.
"""

from __future__ import annotations

from typing import Optional

from .prompt import DEFAULT_CHALLENGE_PROMPT


class ChallengeUnavailable(Exception):
    """No model could run the challenge (no provider configured / the call
    failed). Distinct from "the graph can't resolve it" — the caller must
    surface the honest no-key state, not an escalation."""


# The role tail the resolver appends. Asks the model to refine ONLY when the
# note's own grounding settles the challenge; otherwise to decline so the
# escalation seam (not a fabricated edit) carries the open thread forward.
RESOLVE_OR_DECLINE_PROMPT = """
A note in the user's research is being challenged. Decide whether the
note can be corrected or sharpened *from what it already asserts and its
own grounding* — or whether settling the challenge would need new
research.

Respond with a JSON object only — no prose, no markdown fences:

{
  "resolution": "refine" | "needs_research",
  "refined_text": "<the corrected/sharpened note, only when resolution=refine>"
}

Rules:
- "refine" ONLY when the challenge is answerable without new sources: a
  correction, a hedge the note overstated, a sharper phrasing. The
  refined_text must differ in substance from the original — never restate it.
- "needs_research" when the challenge asks for evidence the note does not
  carry (a source it can't cite, a number it never measured). Leave
  refined_text empty.
- When in doubt, choose "needs_research". A wrong refinement is worse than
  an honest escalation.
""".strip()


def make_dispatch_resolver(
    investigation_id: str,
    *,
    role: str = "challenger",
):
    """Build the production resolver: dispatch the challenger role, parse a
    refine-or-decline verdict. ``None`` return = decline (escalate);
    :class:`ChallengeUnavailable` raised = no model ran (honest no-key).

    Imported callers pass the result straight to
    ``living_note.challenge_note(resolver=...)``. Lazy dispatch import so
    this module stays loadable without the provider stack."""

    def _resolve(current_text: str, challenge_text: str) -> Optional[str]:
        from substrate.dispatch import ProviderError, dispatch  # lazy

        prompt = (
            f"{RESOLVE_OR_DECLINE_PROMPT}\n\n"
            f"The note:\n{current_text}\n\n"
            f"The challenge:\n{challenge_text or DEFAULT_CHALLENGE_PROMPT}"
        )
        try:
            result = dispatch(prompt, role, investigation_id=investigation_id)
        except (ProviderError, KeyError) as exc:
            # No model could run — escalating here would mislabel a config
            # gap as an open research thread. Surface it honestly instead.
            raise ChallengeUnavailable(str(exc)) from exc

        text = getattr(result, "text", "") or ""
        return parse_resolution(text, current_text=current_text)

    return _resolve


def parse_resolution(response_text: str, *, current_text: str) -> Optional[str]:
    """Parse the challenger's refine-or-decline JSON. Returns the refined
    text when the model resolved (and it actually differs from the
    original), else ``None`` (decline → escalate). A malformed response
    declines — a parse failure must never become a fabricated refinement."""
    from roles._json_decode import extract_json_object

    obj = extract_json_object(response_text)
    if not isinstance(obj, dict):
        return None
    if obj.get("resolution") != "refine":
        return None
    refined = obj.get("refined_text")
    if not isinstance(refined, str) or not refined.strip():
        return None
    refined = refined.strip()
    # A "refinement" identical to the note is a no-op dressed as a change.
    if _normalize(refined) == _normalize(current_text):
        return None
    return refined


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())
