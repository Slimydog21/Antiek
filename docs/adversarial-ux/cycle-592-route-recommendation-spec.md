# Adversarial Product/UX Architecture — Cycle 592

**Read-only. No edits. Concrete spec + risks for a deterministic route recommendation layer.**

---

## 1. Current-state audit (what exists, what doesn't)

### What is built and shipping

| Surface | What it does | Where |
|---|---|---|
| Route instrument (Cycle 591) | Server-owned opaque route IDs, preview endpoint, launch-time re-resolution, budget ledger | `research_route.py`, `research_routes.py`, `StartResearch.tsx` |
| Advisory model decision (Settings tab) | Task-based model ranking (7 task types), quality scores, budget eligibility | `advisory_decision.py`, `settings_budget.py`, `Settings/index.tsx` |
| Research tier map | Closed two-value set (fast/deep), thinking-policy differentiation on GLM-5.2 | `research_tier.py` |
| StartResearch UI | Fast/Deep radio group, budget ledger rail, route preview cards | `StartResearch.tsx` |

### What is explicitly NOT built (the gap)

1. **No per-question recommendation.** The UI defaults to "deep" for every question regardless of complexity. The `useEffect` auto-selects the first ready "deep" candidate — a static preference, not an analysis.

2. **No reason codes.** The route preview returns `rationale` (a static string like "GLM-5.2 (thinking enabled) — reasoning-heavy lane for questions worth the deeper reasoning") but nothing that explains WHY a specific question would benefit from one lane over the other.

3. **No bridge between Settings decision-tree and the research flow.** The Settings tab ranks models by task type (deep_research, reading, etc.) with benchmark evidence. The route instrument shows Fast/Deep with readiness. These are parallel systems that never intersect — the research flow has no access to the task-affinity intelligence.

4. **No research-intent elicitation.** The user types a question and gets two route options. There is no mechanism to ask "what kind of answer do you want?" — the system infers nothing about depth, time-sensitivity, or cost-sensitivity from the question itself.

---

## 2. Highest-value non-duplicate UI slice

### The gap, precisely stated

The Settings decision-tree tab answers: "Given a task TYPE (deep_research, reading, etc.) and a cost budget, which tier should I use?" — but it's a Settings page, disconnected from the research flow.

The route instrument answers: "Here are the two available routes — pick one" — but offers zero guidance on which to pick.

**The missing slice: a deterministic, question-analyzing recommendation that lives in the research entry flow, bridging the two systems without duplicating either.**

### What this is NOT

- NOT a new Settings tab (Settings already has the decision tree).
- NOT a raw model dropdown (explicitly rejected by §16).
- NOT an LLM-powered suggestion (zero spend is a hard constraint).
- NOT an override of the existing route instrument (the operator always has final say).

### What this IS

A **Route Recommendation Banner** — a deterministic, heuristic-driven suggestion that appears inline on the route cards in StartResearch, explaining which route the system would pick and why.

---

## 3. Concrete spec: Route Recommendation Banner

### 3.1 Placement and lifecycle

```
[Composer textarea]
[Voice + Attach]
[Route preview loading/error/retry]

┌─────────────────────────────────────────────────────────┐
│ RECOMMENDATION                                          │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Based on your question, Deep lens is recommended.   │ │
│ │                                                     │ │
│ │ Reason codes:                                        │ │
│ │ · Multi-part question (detected 2 sub-questions)    │ │
│ │ · Analytical verb ("evaluate", "compare")           │ │
│ │                                                     │ │
│ │ [Use Deep lens]  [I'll choose myself]               │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ RESEARCH ROUTE                                          │
│ ┌ Fast lens ─ GLM-5.2 · thinking off ┐                  │
│ │ exploratory work · READY            │                  │
│ └─────────────────────────────────────┘                  │
│ ┌ Deep lens ─ GLM-5.2 · thinking on ┐                   │
│ │ reasoning-heavy · RECOMMENDED       │  ← badge        │
│ └─────────────────────────────────────┘                  │
│                                                         │
│ DAILY LEDGER ...                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Heuristic engine (deterministic, zero LLM)

**Location:** `substrate/dispatch/route_recommendation.py` (new file, pure function, no I/O)

**Input:** question string (trimmed), budget state (from `read_operator_budget()`), route readiness (from `route_choices()`)

**Output:** `RouteRecommendation` dataclass:
```python
@dataclass(frozen=True)
class RouteRecommendation:
    tier: ResearchTier           # "fast" or "deep"
    confidence: float            # 0.0-1.0, how strong the signal is
    reason_codes: tuple[str, ...]  # machine-readable codes
    reason_text: str             # human-readable summary
    budget_forced: bool          # True if budget constraint forced the choice
```

**Heuristic signals (in priority order):**

| Signal | Code | Heuristic | Fast→ | Deep→ |
|---|---|---|---|---|
| Question length | `short_question` | < 8 words | ✓ | |
| Question length | `long_question` | ≥ 25 words | | ✓ |
| Sub-question detection | `multi_part` | Count of `?` marks ≥ 2, or semicolons separating clauses | | ✓ |
| Analytical verbs | `analytical_verb` | Contains: evaluate, compare, contrast, analyze, assess, critique, explain why, what are the implications, trace, map | | ✓ |
| Factual verbs | `factual_verb` | Contains: what is, define, list, when did, who is, how many | ✓ | |
| Domain specificity | `domain_specific` | Contains technical/domain terms from a curated set (configurable, starts empty — populated by operator over time) | | ✓ |
| Cost sensitivity | `near_budget_cap` | `remaining_usd < estimated_deep_cost_high` | ✓ | |
| Explicit preference | `user_hint_fast` | Contains: quick, brief, short, fast, overview, summary of | ✓ | |
| Explicit preference | `user_hint_deep` | Contains: thorough, detailed, comprehensive, in-depth, exhaustively, rigorously | | ✓ |

**Scoring:**
- Each signal adds a weight to the "deep" score (positive) or "fast" score (negative).
- Final tier = whichever side has the higher cumulative weight.
- Confidence = `abs(deep_score - fast_score) / max_possible_score`.
- If no signals fire, confidence = 0.0, tier = `DEFAULT_RESEARCH_TIER` ("deep"), reason_codes = `("default",)`.

**Budget-forced override:**
- If `would_exceed_budget` is `True` for the recommended tier, force the cheaper tier.
- Set `budget_forced = True`.
- Add reason code `"budget_cap_forced"`.

### 3.3 API surface

**No new endpoint.** The recommendation runs on the client side, consuming data already available from the route preview response.

**Why client-side:**
- The route preview already returns budget state and readiness.
- The heuristics are pure string analysis — no server-side computation needed.
- Keeps the recommendation responsive (no extra network round-trip).
- The server never sees the recommendation logic (preserves the existing privacy posture — the question is only sent to the preview endpoint, not to a recommendation endpoint).

**Alternative considered and rejected:** Server-side recommendation endpoint (`POST /research/routes/recommend`). Rejected because: (a) it adds a network round-trip before the route cards appear, (b) the heuristics are trivial string analysis that doesn't benefit from server-side state, (c) it would require the server to expose the recommendation logic to adversarial probing.

### 3.4 Frontend integration

**New file:** `apps/reading/src/lib/routeRecommendation.ts`

**Hook:** `useRouteRecommendation(question: string, preview: ResearchRoutePreview | null): RouteRecommendation | null`

**Lifecycle:**
1. `useResearchRoutePreview` fires (existing, debounced 300ms).
2. When preview arrives, `useRouteRecommendation` runs the deterministic heuristics on the trimmed question.
3. If recommendation has `confidence ≥ 0.3` AND the recommended tier is ready, render the banner.
4. If `confidence < 0.3` OR the recommended tier is not ready, suppress the banner (don't recommend with low confidence — that's noise, not signal).
5. "Use [tier]" button: sets `selectedChoiceId` to the recommended candidate's `choice_id` and `tier` to the recommended tier.
6. "I'll choose myself": dismisses the banner (sets a `dismissed` ref, persisted for the session only — not across sessions).

**Badge on route cards:** The recommended route card gets a subtle "RECOMMENDED" badge (small monospace text, aurora color) next to the readiness label.

### 3.5 Mobile behavior

- Banner stacks vertically (already the existing layout at narrow widths).
- "Use [tier]" button is full-width on mobile (< 640px).
- Reason codes use `text-[11px]` (existing sizing for detail text).
- Banner is collapsible via a `<details>` element on mobile to save vertical space — reason codes hidden by default, "Use [tier]" button visible.

### 3.6 Dark mode

- Banner background: `bg-charcoal-2` (existing dark card color).
- Border: `border-charcoal-1` (existing dark rule).
- Text colors: `text-bright` / `text-moonlight` (existing dark mode tokens).
- Badge: `text-aurora` (existing, already dark-mode aware).

### 3.7 Keyboard behavior

- "Use [tier]" button is focusable (tab order after route cards).
- "I'll choose myself" is a button (focusable, Enter/Space activates).
- Banner does not trap focus — it's inline in the existing tab flow.
- Screen reader: `role="status"` on the banner, `aria-live="polite"` so the recommendation announces when it appears.

### 3.8 Operator override

- **"Use [tier]" button:** Applies the recommendation. Does NOT lock the choice — the user can still click a different route card after.
- **"I'll choose myself":** Dismisses the banner. The route cards remain fully functional. Dismissal is session-scoped (not persisted to storage) — refreshing the page re-evaluates.
- **Route card click:** If the user clicks a route card that is NOT the recommended one, the banner silently updates to show "You chose [tier] — the system would have recommended [other tier]" as a non-blocking note. This is informational, not nagging.

### 3.9 Honest budget boundaries

- When all pricing is `0.0` (current state), the budget-forced signal never fires — `would_exceed_budget` is `null` for every candidate.
- The banner renders without budget reasoning when pricing is unknown. It does NOT fabricate cost savings.
- When pricing IS populated: the recommendation checks `would_exceed_budget` from the preview response (already computed server-side). If the recommended tier would exceed the cap, it forces the cheaper tier with reason code `"budget_cap_forced"`.
- The banner never shows "you'll save $X" because trajectory cost is unknown (the existing "projection unknown" discipline).

---

## 4. Stress-test: adversarial challenges

### 4.1 Is this deterministic?

**Yes.** The heuristic engine is a pure function: `str → float → frozenset[str] → RouteRecommendation`. No randomness, no LLM calls, no network I/O. The same question always produces the same recommendation. Unit-testable with a table of (input, expected_tier, expected_codes) tuples.

### 4.2 Is this prompt-sensitive?

**Yes, but bounded.** The heuristics respond to structural features of the question (length, punctuation, verb presence). They are sensitive enough to distinguish "What is the GDP of France?" from "Evaluate the long-term implications of France's fiscal policy on Eurozone stability, considering the 2024 pension reform and its cascading effects on sovereign debt markets."

**What it does NOT do:** It does not parse syntax trees, run NLP pipelines, or understand semantics. It does regex/keyword matching on trimmed text. This is honest — it's a heuristic, not an intelligence.

### 4.3 Is this explainable?

**Yes.** Every recommendation carries `reason_codes` (machine-readable) and `reason_text` (human-readable). The codes map 1:1 to the heuristic signals in the spec table. An operator can read the reason codes and understand exactly why the system recommended what it did.

### 4.4 Does this have zero LLM spend?

**Yes.** The entire recommendation engine is client-side string analysis. No API calls, no model inference, no token consumption. The only network call is the existing route preview endpoint.

### 4.5 Is this non-duplicate with the Settings decision tree?

**Yes.** The differences are structural:

| Dimension | Settings Decision Tree | Route Recommendation |
|---|---|---|
| Location | Settings page (disconnected from research flow) | StartResearch inline (in the research flow) |
| Input | Task type (7 options) + input/output sizes | Question text (natural language) |
| Output | Ranked model candidates with quality scores | Single tier recommendation with reason codes |
| Authority | Advisory (never grants dispatch authority) | Advisory (operator always has final say) |
| Granularity | Per-task-type model ranking | Per-question route suggestion |
| Benchmark integration | Yes (quality scores from Antiek-bench) | No (heuristic-only, no benchmark dependency) |

The Settings tab answers "which tier for this TASK TYPE?". The recommendation answers "which tier for this SPECIFIC QUESTION?". They are complementary, not overlapping.

### 4.6 Edge cases and failure modes

| Edge case | Behavior | Honesty |
|---|---|---|
| Empty question | No recommendation (confidence = 0.0) | Banner hidden |
| Very short question ("AI") | `short_question` fires → Fast recommended with low confidence | Banner shown only if confidence ≥ 0.3 — may be hidden |
| Question with mixed signals ("Briefly evaluate...") | Both `user_hint_fast` and `analytical_verb` fire → net score determines | Reason codes show both signals |
| Question in non-English language | Heuristics are English-only; no signals fire → default (Deep, confidence 0.0) | Banner hidden; no false confidence |
| Question that's a URL only | URL pattern detected → no recommendation | Banner hidden |
| All routes unavailable | No recommendation | Banner hidden |
| Budget at cap, both tiers over | `budget_forced` fires but no tier is affordable → no recommendation | Banner hidden; the "over budget" state is already shown on route cards |
| Recommendation dismissed, question changes | Re-evaluates on new question; dismissal is per-question, not session-global | Correct: changing the question should re-trigger |

### 4.7 What this does NOT do (honest scope boundaries)

1. Does NOT change the default selection behavior. The existing `useEffect` still defaults to "deep". The recommendation is additive, not a replacement.
2. Does NOT block launch. The user can always launch with any ready route, regardless of recommendation.
3. Does NOT persist recommendations. No storage, no telemetry, no "you ignored our recommendation" tracking.
4. Does NOT learn from operator behavior. No feedback loop, no "you always pick Fast so we'll recommend Fast."
5. Does NOT affect the Settings tab. The two systems are independent.
6. Does NOT affect the backend dispatch. The recommendation is purely presentational.

---

## 5. Risks

### Risk 1: False confidence on ambiguous questions

**Severity: MEDIUM**
**Description:** A question like "Tell me about France" could trigger `short_question` (Fast) but the operator might want deep research. The heuristic has no way to know.
**Mitigation:** The confidence threshold (≥ 0.3) suppresses low-confidence recommendations. The operator always has final say. The banner says "recommended," not "required."
**Reconsider if:** Operators report that the recommendation is wrong more than 30% of the time in practice.

### Risk 2: English-only heuristics

**Severity: LOW (for now)**
**Description:** The verb-detection and word-count heuristics assume English. Non-English questions produce no signals → default recommendation (Deep).
**Mitigation:** The default is Deep (the safe baseline for unknown questions). The banner is hidden when confidence < 0.3, so non-English questions simply show no recommendation.
**Reconsider if:** Antiek adds multi-language support.

### Risk 3: Heuristic gaming

**Severity: LOW**
**Description:** An operator who always wants Fast could learn to prepend "Briefly" to every question.
**Mitigation:** This is a feature, not a bug — the heuristic is responsive to explicit user hints. The operator is the authority.
**Reconsider if:** The heuristic becomes a de facto gate rather than a suggestion.

### Risk 4: Stale domain-specific terms

**Severity: LOW**
**Description:** The curated domain-specific term set (initially empty) could rot or become irrelevant.
**Mitigation:** The term set is configurable and starts empty. It only adds value when the operator populates it. An empty set means no `domain_specific` signal fires — the system degrades gracefully.
**Reconsider if:** The term set grows beyond 50 entries without review.

### Risk 5: Client-side logic visibility

**Severity: LOW**
**Description:** Since the heuristic runs in the browser, a technically sophisticated user could inspect the JavaScript and reverse-engineer the scoring logic.
**Mitigation:** The heuristics are intentionally transparent — there's nothing secret about them. The server never sees the recommendation. The opacity is in the route IDs and provider mapping (already server-owned), not in the recommendation logic.
**Reconsider if:** The recommendation logic needs to incorporate server-side state (e.g., historical accuracy metrics).

### Risk 6: Interaction with existing auto-selection

**Severity: MEDIUM**
**Description:** The existing `useEffect` auto-selects the first ready "deep" candidate. The recommendation might suggest "fast," creating a visual conflict where the banner says Fast but the radio is on Deep.
**Mitigation:** The "Use [tier]" button explicitly sets `selectedChoiceId` and `tier`, overriding the auto-selection. If the user doesn't click the button, the auto-selection remains — the banner is informational, not authoritative.
**Reconsider if:** Users report confusion about the mismatch between recommendation and auto-selection.

### Risk 7: Scope creep into per-call routing

**Severity: HIGH (if it happens)**
**Description:** The temptation to extend this logic beyond the research entry point — e.g., recommending tiers for individual cascade sub-questions, or for book QA.
**Mitigation:** The spec explicitly scopes this to StartResearch only. The heuristic module is importable but not wired into any other surface. Adding it elsewhere requires a new spec.
**Reconsider if:** Never. The closed two-value set at research entry is the intentional boundary.

---

## 6. Implementation checklist (if this were to be built)

### Sprint 1: Heuristic engine + tests

**Files:**
- `substrate/dispatch/route_recommendation.py` (new, ~120 lines)
- `tests/test_route_recommendation.py` (new, ~200 lines)

**Milestones:**
1. `RouteRecommendation` dataclass with `tier`, `confidence`, `reason_codes`, `reason_text`, `budget_forced`.
2. `recommend_route(question, budget_state, route_readiness)` pure function.
3. Heuristic signal table (9 signals, each with code, regex/keyword list, weight).
4. Budget-forced override logic.
5. Unit tests: 20+ cases covering all signals, mixed signals, budget forcing, non-English, empty input, URL-only input.

**Acceptance criteria:**
- `recommend_route` is a pure function (no I/O, no side effects).
- Same input always produces same output (deterministic).
- All reason codes from the spec table are testable.
- Budget-forced override fires when `would_exceed_budget` is True for the recommended tier.

### Sprint 2: Frontend integration

**Files:**
- `apps/reading/src/lib/routeRecommendation.ts` (new, ~80 lines)
- `apps/reading/src/hooks/useRouteRecommendation.ts` (new, ~30 lines)
- `apps/reading/src/modes/ResearchWorkstation/StartResearch.tsx` (modified, ~40 lines added)

**Milestones:**
1. `recommendRoute()` TypeScript implementation matching the Python spec.
2. `useRouteRecommendation` hook consuming question + preview.
3. Banner component with reason codes, "Use [tier]" button, "I'll choose myself" button.
4. "RECOMMENDED" badge on the recommended route card.
5. Confidence threshold gating (≥ 0.3).
6. Mobile responsive layout (stack at < 640px).
7. Dark mode tokens.
8. Keyboard navigation (tab order, Enter/Space).
9. Screen reader (`role="status"`, `aria-live="polite"`).
10. Dismissal state (session-scoped ref).

**Acceptance criteria:**
- Banner appears when confidence ≥ 0.3 and recommended tier is ready.
- "Use [tier]" sets the correct route card selection.
- "I'll choose myself" hides the banner.
- Mobile: banner stacks vertically, button is full-width.
- Dark mode: all text readable, no hardcoded colors.
- Keyboard: full tab navigation, no focus traps.
- Screen reader: recommendation announced on appearance.

### Verification gates

- `python -m pytest tests/test_route_recommendation.py -q` — all pass.
- `npx tsc -b` — no type errors.
- `npx playwright test` — existing tests still pass.
- Manual: type "What is GDP?" → Fast recommended. Type "Evaluate the long-term implications of..." → Deep recommended. Type "AI" → no recommendation (low confidence).

---

## 7. Why this is worth building

The current route instrument is honest and functional — but it asks the operator to make a decision with zero guidance. The Settings decision tree has intelligence but lives in the wrong place (a configuration page, not the research flow). This recommendation bridges the gap at the exact moment of decision: when the operator is typing their question and about to launch.

The zero-LLM constraint makes this buildable in one sprint. The deterministic heuristics are testable, explainable, and overridable. The confidence threshold prevents noise. The honest scope boundaries prevent scope creep.

The risk profile is low: the recommendation is advisory-only, the operator always has final say, and the existing behavior is unchanged if the banner is removed. This is the minimum viable intelligence that makes the route instrument feel guided rather than arbitrary.
