# arXiv T2 (CC-BY-NC) serving — the body-emission ceiling is {T1}

**Decision date:** 2026-05-30 (SPR-02, arxiv-ingest, M1 reconciliation; sharpened round 2)
**Status:** ✅ Implemented — `_BODY_SERVABLE_TIERS = {T1}` in `substrate/rights/arxiv_tiers.py`. The gated→permissive flip to `{T1, T2}` is the one-line future reversal (see below), contingent on counsel + a non-commercial serving mode.
**Owner:** SPR-02 rights / serve-tier engine
**Gate:** the §9.0 / counsel legal gate (plus a genuine non-commercial serving mode) is what would later promote T2 to body-servable; until both, {T1} stands.

## The two questions, kept separate

There are two distinct rights questions, and conflating them is the bug this
note pins down:

1. **May a full body be EMITTED/DISPLAYED from Antiek storage at all, on the
   current (commercial) surface?**
   This is the body-emission ceiling owned by `body_servable` /
   `guard_servable_body` (and the SPR-02 serving-boundary guard
   `serve_full_text_guarded`). On today's ad-funded surface the answer is
   **{T1}**.
2. **May ads run on the body (commercial exploitation)?**
   This is the commercial gate owned by `ads_allowed`
   (`substrate/rights/ad_eligibility.py`). The answer is **{T1}**.

Today the two ceilings COINCIDE at {T1}. They are kept as *separate* predicates
because the *future* gated→permissive flip (question 1 widening to {T1, T2})
would split them: a T2 body would become display-servable while ads stay
T1-only. T2 sits in that future gap. It does NOT sit in the current gap — on the
current commercial surface a T2 body is not emittable at all.

## Why {T1} and not {T1, T2} for body emission — the BINDING posture

The repo's **canonical, already-shipped license resolver**
`acquisition/licenses_core.py` (`CC_LICENSE_ROWS`, the
`creativecommons.org/licenses/by-nc` row) resolves CC-BY-NC to
`redistributable=False` + `GATED_DEFAULT_CONTENT_CLASS`, with the explicit,
binding rationale:

> *"NC forbids commercial reuse; Antiek's ad-funded serving is commercial ->
> gated. Reverse if Antiek adds a non-commercial serving mode or a per-license
> commercial-use determination."*

So the binding posture is already settled in shipped code: **a commercial,
ad-funded platform may NOT emit a CC-BY-NC (T2) body.** A `body_servable(T2) =
True` ceiling would directly contradict that resolver and break
single-source-of-truth — an auditor would get `redistributable=False` / gated
from `licenses_core` but `body_servable = True` from the rights engine, two
divergent verdicts on the same license. The {T1} reading keeps the rights engine
and the resolver saying the SAME thing.

Three reinforcing reasons:

- **Single source of truth.** `acquisition/licenses_core.py` is the one legal
  home for CC semantics (per its own module docstring). The rights engine
  DERIVES from it and must not overrule it. CC-BY-NC is gated there; T2 is
  therefore not body-servable here.
- **Deny-by-default on a genuinely ambiguous legal question.** Whether a
  primarily-commercial actor serving an NC body (even ad-free) is "directed
  toward commercial advantage" is fact-specific and has been litigated to
  inconsistent outcomes — it is not a bright line. A wrong promotion of a body
  out of storage is the *cardinal* redistribution violation; the conservative
  {T1} reading biases the ambiguous case to deny, which is the whole posture of
  this rights model.
- **The commercial-surface fact.** Antiek serves full text behind a per-second
  ad border with a payout split — an ad-funded, commercial context. NonCommercial
  forbids commercial reuse; emitting an NC body from this surface is the
  conservative-deny case, not the conservative-allow case.

## What the {T1, T2} "non-commercial display" reading actually is — a FUTURE state

The {T1, T2} world ("a T2 body may be displayed for non-commercial in-app
reading") is NOT today's default. It is a future state contingent on **BOTH**:

- **(a)** `licenses_core`'s own *"Reverse-if"* condition being met — Antiek
  building a **genuine non-commercial serving mode** (a surface where the NC body
  is displayed with no ad border, no payout, no commercial advantage); AND
- **(b)** **§9.0 / counsel sign-off** that such a mode satisfies NonCommercial
  for a primarily-commercial operator.

Neither holds today. The non-commercial serving mode does not exist; counsel has
not ruled. So {T1, T2} is the post-Reverse-if future, not the current default.

## Divergence from the SPR-02 / SPR-04 sprint-page wording (recorded honestly)

This decision **DIVERGES** from two pieces of sprint-page wording, and the
divergence is deliberate:

- The **SPR-02 page** (Goal + M2) literally states the body-serve ceiling as
  `{T1, T2}`.
- **SPR-04** describes "T2 bodies may be fetched for in-app non-commercial
  reading."

Both describe the **post-Reverse-if future** — the world where the
non-commercial serving mode exists and counsel has blessed it. But the
**shipped** resolver (`acquisition/licenses_core.py`) gates NC **today**, and
single-source-of-truth + deny-by-default mandate that the rights engine match the
shipped resolver, not a future sprint-page aspiration. So the engineering default
is `{T1}` now, and the sprint pages' `{T1, T2}` is the documented target the
one-line reversal below reaches once its preconditions are met. Recording the
divergence here (rather than silently shipping `{T1, T2}` against the resolver,
or silently shipping `{T1}` with no trace of the sprint wording) is the honesty +
defensibility bar: an auditor asking "why does the rights engine deny a T2 body
when SPR-02 says {T1,T2}?" lands on this note.

## The one-line reversal (gated → permissive)

If (a) Antiek builds a genuine non-commercial serving mode AND (b) counsel rules
that serving NC bodies in that mode is not "commercial use", the flip from the
gated `{T1}` posture to the permissive `{T1, T2}` posture is a single edit in
`substrate/rights/arxiv_tiers.py`:

```python
_BODY_SERVABLE_TIERS: frozenset[RightsTier] = frozenset(
    {RightsTier.T1_REDISTRIBUTABLE, RightsTier.T2_NON_COMMERCIAL}
)
```

`_BODY_SERVABLE_TIERS` is deliberately a single named frozenset (not a scattered
`tier in {...}` literal) precisely so this stays a one-line, one-place flip. The
direction that needs sign-off is the **gated→permissive** one (`{T1}` →
`{T1, T2}`): it requires counsel, a non-commercial serving mode, AND a
reconciliation of `acquisition/licenses_core.py:CC_LICENSE_ROWS` (the CC-BY-NC
row must flip in lockstep, or the two homes drift). The body-emission guard and
all its callers re-read the frozenset; the ad gate stays `{T1}`-only and is
unaffected. The SPR-02 invariant tests (`tests/test_arxiv_rights_invariant.py`)
state the expected ceiling as `_EXPECTED_BODY_SERVABLE` — flipping the constant
requires updating that expectation too, which makes the reversal a deliberate,
reviewed act rather than an accident.
