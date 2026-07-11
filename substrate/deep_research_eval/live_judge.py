"""Live ``JudgeFn`` adapter for the W0 deep-research eval harness.

The harness (``runner.run_eval``) takes an injected ``JudgeFn`` —
``Callable[[str], str]`` — that maps a rubric prompt (built by
``rubric.build_judge_prompt``) to the judge model's RAW text response, which
``rubric.parse_judge_response`` then parses strictly. This module supplies the
one live implementation of that callable, backed by the existing dispatch
``AnthropicProvider``. It adds NO HTTP client and NO new dependency: it only
calls ``provider.call(...)`` and forwards ``response.text`` unchanged.

Two invariants make the adapter safe to feed I-9's "two comparable weekly runs":

Model-pin integrity (comparability contract)
    The adapter uses EXACTLY ``rubric.JUDGE_MODEL_ID``. A different judge model
    silently changes the comparability key and corrupts I-9, so a caller that
    tries to configure any other model is REFUSED at construction (``ValueError``
    from ``__post_init__``). The pinned constant — not a caller-supplied string —
    is what is passed to the provider on every call.

Fail-closed to NOT_MEASURED (the core honesty property)
    ANY failure path — provider exception, timeout, HTTP error, a NON-COMPLETE
    ``finish_reason`` (truncation etc.), empty/whitespace response, or a
    non-``str`` response — is converted into a documented sentinel string
    (``LIVE_JUDGE_ERROR_SENTINEL``) that ``parse_judge_response`` is guaranteed
    to REJECT (it is not JSON). The runner then records that query as
    ``NOT_MEASURED`` with ``judge_scores=None`` — never a fabricated or default
    score, never a fallback to a different model, never a retry into a different
    model. A valid-looking judgment is passed through byte-for-byte with no
    pre-parsing or "fix-up": the harness's strict parser stays the single source
    of truth for what counts as MEASURED. The JudgeFn ALWAYS returns a ``str``,
    so it can never trip the runner's ``isinstance(raw_judgment, str)`` guard
    (which would otherwise raise ``TypeError`` and crash the whole run). Even the
    error handler is hardened: it never trusts a hostile exception ``__repr__`` /
    ``__str__`` (see ``_describe_exception``), so the JudgeFn cannot raise.

    Truncation guard: the adapter admits the response text to the parser ONLY
    when ``finish_reason`` is a known-complete stop (``_COMPLETE_FINISH_REASONS``
    = ``{"stop", "end_turn", "stop_sequence"}``). A provider-declared partial
    stop — Anthropic's ``"max_tokens"``, the normalized ``"length"``,
    ``"content_filter"``, ``"tool_use"``, ``None``, or any unrecognized value —
    fails closed EVEN IF the truncated JSON happens to parse, because a partial
    judgment is not a trustworthy score.

Injectable client (offline testing)
    The factory takes an already-constructed provider — any object satisfying the
    narrow :class:`JudgeProvider` protocol below (a single ``call(...)`` method).
    The dispatch ``AnthropicProvider`` satisfies it STRUCTURALLY, so production
    injects a real one and this adapter reuses it verbatim — no new HTTP client,
    no new dependency. Tests inject a stub, so no real network is touched. A LIVE
    run happens ONLY when the operator supplies a real ``AnthropicProvider`` plus
    a valid ``ANTHROPIC_API_KEY`` — this module closes the code gap but is itself
    operator-key gated and does not run any eval.

    The protocol is defined locally (rather than importing dispatch's broader
    ``Provider``) on purpose: the JudgeFn needs only ``.call()``, so the eval
    harness stays decoupled from the rest of the dispatch package's surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .rubric import JUDGE_MODEL_ID
from .runner import JudgeFn


class _JudgeResponse(Protocol):
    """The two fields the adapter reads off a provider response: the raw text
    and the completion signal (``finish_reason``). A truncated/incomplete
    judgment is untrustworthy even when its partial text happens to parse, so
    the adapter must inspect ``finish_reason`` and fail closed on anything that
    is not a known-complete stop."""

    text: str
    finish_reason: str | None


class JudgeProvider(Protocol):
    """The narrow slice of the dispatch ``Provider`` contract the judge needs.

    A dispatch ``AnthropicProvider`` satisfies this structurally (its ``call``
    has this exact keyword signature and returns a ``RawProviderResponse`` whose
    ``.text`` is a ``str`` and ``.finish_reason`` is ``str | None``). Injecting
    one is the production path; a stub is the test path.
    """

    def call(
        self, *, model: str, prompt: str, max_tokens: int, temperature: float
    ) -> _JudgeResponse: ...

# A judge response that ``rubric.parse_judge_response`` is guaranteed to reject
# (it is not valid JSON), so every failure funnels to the runner's NOT_MEASURED
# path instead of a fabricated score. The reason is appended for debugging only.
LIVE_JUDGE_ERROR_SENTINEL = "LIVE_JUDGE_ERROR"

# Known-COMPLETE finish reasons — the ONLY values that admit the response text
# to the parser. Conservative allow-list, not a deny-list: anything not in here
# (``"max_tokens"``/``"length"`` truncation, ``"content_filter"``, ``"tool_use"``,
# ``None``, or any unrecognized value) fails closed → NOT_MEASURED. Two spellings
# are accepted because the dispatch ``AnthropicProvider`` forwards Anthropic's
# RAW ``stop_reason`` un-normalized (``"end_turn"``/``"stop_sequence"``) while the
# base ``RawProviderResponse`` documents a normalized ``"stop"``; both mean the
# model finished on its own and the text is complete.
_COMPLETE_FINISH_REASONS = frozenset({"stop", "end_turn", "stop_sequence"})

# Defaults for the single judge call. temperature=0 keeps the judge as stable as
# the provider allows (comparability); max_tokens comfortably covers the tiny
# strict-JSON object the rubric asks for.
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.0


def _fail_closed(reason: str) -> str:
    """Return a parser-rejected sentinel string → runner marks NOT_MEASURED."""
    return f"{LIVE_JUDGE_ERROR_SENTINEL}: {reason}"


def _describe_exception(exc: BaseException) -> str:
    """Build a fail-closed reason WITHOUT trusting the exception's ``__repr__``
    or ``__str__`` (a hostile one can raise). ``type(exc).__name__`` never runs
    user code; detail extraction is isolated so its failure cannot escape."""
    name = type(exc).__name__
    try:
        detail = str(exc)
    except Exception:  # a hostile __str__ must not crash the eval run
        return f"provider call failed: {name}: <undisplayable exception detail>"
    return f"provider call failed: {name}: {detail}"


@dataclass(frozen=True)
class LiveJudge:
    """Callable ``JudgeFn`` backed by a dispatch ``Provider``, pinned to
    ``JUDGE_MODEL_ID`` and fail-closed to NOT_MEASURED.

    Construct via :func:`build_live_judge` (or directly). Refuses any model
    other than the pin at construction. Calling it with a rubric prompt returns
    the model's raw text on success, or a parser-rejected sentinel on any error.
    """

    provider: JudgeProvider
    model: str = JUDGE_MODEL_ID
    max_tokens: int = _DEFAULT_MAX_TOKENS
    temperature: float = _DEFAULT_TEMPERATURE

    def __post_init__(self) -> None:
        # Model-pin integrity: refuse construction with a non-pinned model.
        if self.model != JUDGE_MODEL_ID:
            raise ValueError(
                f"LiveJudge is pinned to the comparability judge {JUDGE_MODEL_ID!r}; "
                f"refusing model {self.model!r}. A different judge model silently "
                "changes the I-9 comparability key and corrupts weekly-run comparison."
            )

    def __call__(self, prompt: str) -> str:
        # Assert the model actually used equals the pin. __post_init__ already
        # guarantees this on a frozen instance; the explicit pass of the pinned
        # constant makes the used model independent of any field tampering.
        assert self.model == JUDGE_MODEL_ID  # comparability invariant (post_init-guaranteed)
        try:
            response = self.provider.call(
                model=JUDGE_MODEL_ID,
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            # Truncation guard: a provider-declared incomplete stop (e.g.
            # ``max_tokens``) yields an UNTRUSTWORTHY partial judgment even when
            # the partial text happens to parse. Fail closed regardless of text.
            finish_reason = response.finish_reason
            if finish_reason not in _COMPLETE_FINISH_REASONS:
                return _fail_closed(f"non-complete finish_reason: {finish_reason!r}")
            text = response.text
            # ``isinstance`` also guards a misbehaving provider that returns a
            # non-str despite the type (empty / whitespace → NOT_MEASURED too).
            if not isinstance(text, str) or not text.strip():
                return _fail_closed("empty or non-text judge response")
            # Raw pass-through: hand the parser the model's text unmodified. No
            # pre-parsing, no fix-up — the strict rubric parser is the sole
            # arbiter of MEASURED vs NOT_MEASURED.
            return text
        except Exception as exc:  # fail closed on ANY provider failure
            # Provider exception / timeout / HTTP error / ProviderError →
            # NOT_MEASURED. ``_describe_exception`` never trusts a hostile
            # ``__repr__``/``__str__``, so the handler itself cannot raise.
            return _fail_closed(_describe_exception(exc))


def build_live_judge(
    provider: JudgeProvider,
    *,
    model: str = JUDGE_MODEL_ID,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    temperature: float = _DEFAULT_TEMPERATURE,
) -> JudgeFn:
    """Build a live ``JudgeFn`` pinned to ``JUDGE_MODEL_ID`` and fail-closed.

    Args:
        provider: An injected dispatch ``Provider`` (production: a real
            ``AnthropicProvider`` with a configured ``ANTHROPIC_API_KEY``; tests:
            a stub). No network is touched here — the JudgeFn calls it lazily.
        model: MUST equal ``JUDGE_MODEL_ID``; any other value raises ``ValueError``
            (guards the I-9 comparability key). Exposed only so a caller can pass
            the pin explicitly and self-document intent.
        max_tokens: Cap for the single judge call.
        temperature: Sampling temperature for the judge call (0 by default).

    Returns:
        A ``JudgeFn`` that returns the judge's raw text on success, or a
        parser-rejected sentinel string on any failure so the runner records
        NOT_MEASURED rather than a fabricated score.
    """
    return LiveJudge(
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
