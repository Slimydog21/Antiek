# RLM integration spec for Antiek

Author: Loop-2 working draft, 2026-05-17

This spec defines how Recursive Language Models (RLMs) — the inference
paradigm formalized by Zhang/Kraska/Khattab (MIT CSAIL, *Recursive
Language Models*, arXiv 2512.24601v3) and productionalized by Prime
Intellect (Sebastian, *Recursive Language Models: the paradigm of
2026*) — slot into Antiek as a first-class substrate primitive rather
than a parallel scaffold.

It is opinionated. Where there is a choice, this spec picks one and
records the reasoning. Where there is real ambiguity, §6 surfaces it
for the operator to ratify before Sprint 11 begins.

The implementation is the *what*; this document is the *why* and the
*where*.

---

## 0. Executive summary

An RLM is not "an LLM that calls itself." It is a specific inference
contract with four load-bearing properties:

1. **The user prompt is exposed as a variable in an external
   environment (a Python REPL), not loaded into the model's context
   window.** The root model sees only constant-size metadata about the
   prompt — length, a short prefix, and how to access parts of it.
2. **The model's output is extracted from a named variable
   (`answer["content"]`), not generated as the model's terminal
   autoregressive output.** Output length is unbounded by context
   window.
3. **Sub-LLM calls are programmatic** — `llm_query(prompt)` and
   `llm_batch(prompts)` inside the REPL — not verbalized actions in
   the orchestrator's stream. Sub-calls can be parallelized and can
   themselves be RLMs (recursion depth ≥ 1).
4. **Tools (web search, retrieval, file fetch) are usable only by
   sub-LLMs, not by the root.** This keeps the root's context window
   clean of verbose tool output.

The paradigm matters for Antiek because three of the four flows the
operator has explicitly named — pasting a long PDF and wrestling with
it, deep research across an open corpus, and synthesis under
constraint with many sub-questions — all hit the same wall: a fixed
context window plus context-rot as length grows. The substrate
solutions already in place (chunking, embedding-grounded retrieval,
context-pack budgets) work for short-context cases. For long-context
cases the substrate needs RLM as the orchestration primitive that lets
the *role* manage its own context rather than relying on a pre-built
context pack.

What is already integrated, from Sprint 9:

- `interfaces/research/rlm_repl.py` — the REPL execution sandbox.
  Full `RLMRepl` class, AST validator, `FunctionRegistry`,
  `ReplSummary`, `rlm_loop` driver, `make_llm_query` /
  `make_llm_batch` helpers. Implements all three invariants of the
  RLM paradigm (variables not context, output extracted from
  `answer`, sub-calls programmatic).
- `substrate/graph/rlm_tools.py` — sub-LLM tool-calling. `SubLLMWithTools`
  class, three built-in tools (`web_search`, `fetch_url`,
  `search_graph`), `equipped_llm_batch` parallel dispatcher,
  `CATEGORY_TOOL_MAP` for DAG-node-category → tool routing.
- `interfaces/research/rlm_dag.py` — decomposition DAG primitives.
  `plan_dag`, `topological_layers`, `execute_dag` with verification +
  retry + hedging, `classify_complexity`. Engine, not visualizer.
- `skills/verification/rlm.py` — RLM-flavored verification via
  rephrased re-dispatch + agreement counting.

What is NOT yet integrated, and what this spec scopes:

- No bridge handler uses the RLM REPL as its execution substrate. The
  five role bridges (wrestling, grounding, decomposer,
  evidence_retriever, parameter_extractor, connector, synthesizer)
  all dispatch a single LLM call against a pre-rendered context.
- The wrestling bridge cannot handle PDFs whose region context
  exceeds the synthesizer's context budget. Today it would either
  truncate or refuse.
- The Loop 1 orchestrator's 9-phase chain has no entry point for
  open-ended questions that don't decompose into 4–8 typed
  sub-questions.
- `llm_batch` parallelism is not exposed at the role level — only
  inside `equipped_llm_batch` for the connector's sub-LLM-with-tools
  pattern.
- Tool-isolation discipline (paper §2 design choice #3) is not
  structurally enforced for the bridges that currently mix LLM calls
  and tool calls inline.
- Verifiers-shaped environment exists only for the decomposer; the
  other four roles need analogous wrappers if RLM trajectories are to
  be trained against.

The spec sequences these gaps into four work items, each closeable in
a single sprint, with no architectural prerequisites beyond what
substrate is in place today.

---

## 1. The RLM contract, restated for Antiek

Before the integration plan, a precise summary of what we are
committing to. This is the contract Sprint 11+ code must hold.

### 1.1 The five-line algorithm (paper §2, Algorithm 1)

```
state   ← InitREPL(prompt=P)
state   ← AddFunction(state, sub_LLM_M)
hist    ← Metadata(state)
while True:
    code              ← LLM_M(hist)
    (state, stdout)   ← REPL(state, code)
    hist              ← hist || code || Metadata(stdout)
    if state[Final] is set:
        return state[Final]
```

Antiek's `rlm_repl.RLMRepl` + `rlm_loop` already implement this.
What's missing is the bridges that call it.

### 1.2 The four properties, with Antiek mappings

| Property | What it means | Antiek surface |
|---|---|---|
| Symbolic prompt | Prompt P lives in `state["prompt"]`, not in `hist` | `RLMRepl(corpus={"prompt": ...})` already supports this |
| Output extraction | Final answer pulled from `state["answer"]["content"]` | `rlm_loop` exits when `answer["ready"]==True`; cap at `RLM_ANSWER_CONTENT_MAX` |
| Programmatic recursion | Sub-calls are Python function calls inside the REPL | `make_llm_query` / `make_llm_batch` wire dispatch as the callable |
| Tool isolation | Tools attach to sub-LLMs only | `SubLLMWithTools.register_tool` — root LLM sees no tools |

### 1.3 The bounded constants

From Paper 2 + Antiek's `substrate/constants.py` (Section F):

| Constant | Value | Source |
|---|---|---|
| `RLM_MAX_RECURSION_DEPTH` | 1 | Antiek default; paper depths 1–2 dominate; depth 3 risks runaway |
| `RLM_ANSWER_CONTENT_MAX` | 1,000,000 chars | Antiek |
| `RLM_REPL_STDOUT_TRUNCATE` | 8,192 bytes | Antiek (paper says "user-adjustable", default 8192) |
| `RLM_LLM_BATCH_MAX_PARALLELISM` | 1 | Antiek (sequential default; bump per role) |
| `RLM_LLM_BATCH_CHARS_TARGET` | 200,000 | Antiek (chunked batches over per-atom calls) |
| `RLM_VERIFY_AGREEMENT_MIN` | 2 | Antiek (verification skill) |
| `RLM_VERIFY_REDISPATCH_COUNT` | 1 | Antiek |
| `RLM_REPL_AVAILABLE_PACKAGES` | duckdb, numpy, sentence_transformers, requests, json, re, hashlib | Antiek |

One new constant this spec proposes:

| New constant | Value | Why |
|---|---|---|
| `RLM_REPL_PER_CALL_TIMEOUT_SECONDS` | 120 | Paper 2 default; prevents runaway LLM-generated code |
| `RLM_DOC_RLM_THRESHOLD_TOKENS` | 64,000 | Wrestling bridge switches to RLM mode when document exceeds this |

---

## 2. What's already in place (audit)

The Sprint 9 migrations were not anticipatory — they were direct ports
of Researchmaxx's RLM machinery before this spec was written. The
audit below records what shape that machinery actually has, against
the contract above.

### 2.1 `interfaces/research/rlm_repl.py` — the REPL sandbox

Status: **complete for the root-side execution path.**

Implements:

- `FunctionRegistry` — whitelist of callables visible inside the
  sandbox. Required for the "sub-LLM as injected function" pattern.
- AST validator — `_ALLOWED_NODE_TYPES` frozenset rejects `try`,
  `with`, `class`, `lambda`, `async`, etc. before any execution.
- `RLMRepl` class with `execute(code)` — single-dict exec so top-level
  assignments land in `sandbox_globals` and the post-exec pullback
  surfaces them in `summarise()`. Curated `__builtins__` allowlist (no
  `open`, no `eval`, no `exec`, no `__import__`).
- `ReplSummary` — constant-size metadata: iteration count, depth,
  `answer["content"]` length/prefix/ready, per-variable
  sizes/types/120-char prefixes, last 8KB of stdout, exception trace.
  `format_for_prompt()` renders as markdown for the next LLM turn.
- `rlm_loop(repl, generate_code)` — drives the while-loop until
  `answer["ready"]` or iteration cap. Force-flushes ready=True on cap
  so callers never get stuck.
- `make_llm_query` / `make_llm_batch` — wrap raw LLM callers into the
  REPL signatures. `make_llm_batch` uses `ThreadPoolExecutor` bounded
  by `max_parallel`, preserves input order.

What's missing at this layer:

- **Per-call timeout enforcement.** The Antiek REPL captures
  exceptions but doesn't bound execution time. Paper 2 specifies 120s
  per REPL call. Add `signal.alarm` or `concurrent.futures` wrapper.
- **Sandbox isolation.** Antiek's sandbox restricts the AST but
  doesn't run code in a separate process. For untrusted prompts
  (operator-supplied), this is fine. For RLM-generated code that
  could in principle write to disk or hit the network via `requests`,
  this is the threat model that Prime Intellect's Sandboxes
  abstraction addresses. Out of scope for Antiek Sprint 11; revisit
  when RLM is exposed to non-operator inputs.

### 2.2 `substrate/graph/rlm_tools.py` — sub-LLM tool-calling

Status: **complete for the sub-LLM-with-tools pattern.**

Implements:

- `SubLLMWithTools` class with `register_tool` /
  `register_builtin(name)` / `register_builtins(names)`.
- Three built-in tools:
  - `web_search(query)` — SerpAPI when `SERPAPI_API_KEY` is set, else
    DuckDuckGo HTML scrape. Returns top-5 formatted snippets.
  - `fetch_url(url)` — httpx with `_extract_text_from_html` regex
    stripper. Truncates at 5,000 chars.
  - `search_graph(query, top_k=5)` — wraps
    `substrate.graph.search.search` with a read-only connection.
- `run(prompt)` — drives the tool-calling loop: build system prompt
  with tool descriptions → per round, parse JSON for `final_answer`
  or `tool_call` → on max-rounds, force a synthesis call.
- `equipped_llm_batch(tasks, ...)` — parallel sub-LLM dispatcher.
- `CATEGORY_TOOL_MAP` + `tools_for_category` — DAG-node-category →
  tool list mapping. Used by the connector role.

What's missing:

- **No bridge consumes this as an RLM substrate.** Today
  `SubLLMWithTools.run` is called directly by the connector bridge as
  a one-shot, not via `RLMRepl.execute`. To honor tool-isolation
  property #4 (tools attach to sub-LLMs), the wrestling bridge in
  Sprint 11 should construct a `SubLLMWithTools` and pass *its*
  `__call__` as the sub-LLM callable to the root RLM's REPL.

### 2.3 `interfaces/research/rlm_dag.py` — decomposition DAG

Status: **complete for the structured decomposition path.**

Implements:

- `DagNode` / `Dag` dataclasses with `to_dict` / `from_plan_json`
  round-trip.
- `topological_layers(dag)` — BFS layering with unresolvable-nodes
  fallback in the final layer.
- `plan_dag(question, *, llm_call, examples=...)` — calls an LLM to
  produce a plan, parses to a Dag.
- `execute_dag(dag, *, llm_call, ...)` — layer-by-layer solver with
  per-node verification (via `skills.verification.rlm.verify_claim`),
  retry with failure context, `[HEDGED]` hedging on final retry
  failure.
- `classify_complexity` — O(1) / O(N) / O(N²) heuristic.
- CLI: `plan` / `layers` / `complexity`.

What's missing:

- **Integration with the role chain.** The DAG is a standalone tool
  the operator can invoke; it's not what the Loop 1 orchestrator
  uses. For the "open-ended exploration" investigation kind (Sprint
  13), `execute_dag` becomes the natural orchestrator. For the
  canonical 9-phase Loop 1, the role chain is the right shape.

### 2.4 `skills/verification/rlm.py` — RLM-flavored verification

Status: **RLM-*flavored*, not full RLM.** Naming clarified here for
the architecture notes.

Implements:

- `verify_with_redispatch` — calls a role twice with rephrased
  instructions, counts agreements, returns verdict.
- `verify_claim` — claim-level verification via 3 rephrased framings
  (direct / extract / adversarial), majority vote with tie-breaker.
- `verified_answer` — claim + plausibility gate.
- Plausibility checks: `check_numeric_range`, `check_sign`,
  `check_units_rough`, `check_expected_shape`.

What's NOT RLM:

- No REPL. No symbolic recursion. No `answer` variable. This is the
  rephrased-redispatch reliability technique that the paper cites as
  "the empirically strongest published reliability mechanism," but it
  predates RLM. Keep the name `skills/verification/rlm.py` for
  Researchmaxx-migration continuity, but in the spec text use
  "RLM-flavored verification" so the distinction stays clear.

### 2.5 Constants (`substrate/constants.py` Section F)

All seven RLM constants from Researchmaxx are migrated. The two new
constants this spec proposes (`RLM_REPL_PER_CALL_TIMEOUT_SECONDS` and
`RLM_DOC_RLM_THRESHOLD_TOKENS`) belong in Section F or a new Section I
"RLM bridges (Sprint 11+)".

---

## 3. The integration gaps, ranked by load-bearingness

In descending order of how blocking the gap is for the operator's
Sprint 1 vision:

### 3.1 [LOAD-BEARING] Long-document wrestling

The operator's Sprint 1 brief described pasting a PDF and "asking for
distillations, then pushing with specific questions, and challenging
the grounding of some facts." The current wrestling bridge handles
this correctly for documents whose region of interest plus
synthesizer context budget fit in 64K-128K tokens. For larger PDFs
(books, dissertations, multi-paper corpora, full SEC filings),
either:

a) The region selection is small enough that the bridge ignores the
   rest of the document — useful for chunk-local questions, useless
   for "summarize chapter 4 against the methodology in chapter 2."

b) The user asks a cross-section question and the bridge has no way
   to handle it. Today it would emit a distillation against the
   region only, which is wrong.

The fix is RLM-as-bridge: load the full document as `prompt` in the
REPL, let the synthesizer (now operating as an RLM root) write code
to slice and re-call itself per section.

### 3.2 [LOAD-BEARING] Long-corpus synthesis in Loop 1

For Loop 1 investigations where Phase 6 synthesis receives a
substrate block exceeding the synthesis-tier context budget (256K
tokens by default), today's bridge truncates. An RLM-wrapped
synthesizer treats the substrate block as `prompt` and dispatches
sub-LLMs per sub-question's evidence pack.

This is the same architectural fix as 3.1 applied to a different role
boundary.

### 3.3 [STRUCTURAL] Tool isolation discipline

Paper §2 design choice #3: tools must be sub-LLM-only. The current
Antiek bridges that need tools (the connector for graph traversal,
the eventual web-search-equipped synthesizer) don't enforce this. The
discipline matters because mixing tool output and root reasoning is
exactly what context-rot exploits.

The fix is mechanical: whenever a bridge needs a tool, the tool
attaches to a `SubLLMWithTools` instance, and the root sees only the
sub-LLM's structured return value.

### 3.4 [OPEN-ENDED] RLM as an alternative Loop 1 orchestrator

Loop 1's 9-phase chain assumes the question decomposes cleanly into
4–8 typed sub-questions. For open-ended questions ("explore this
corpus and find what's interesting," "what's the right framing for
this problem," "summarize this entire investigation's accumulated
evidence into a brief"), the decomposer is the wrong primitive.

The fix is a parallel orchestrator: `investigation_kind="rlm"`
spawns an RLM root that drives sub-call patterns dynamically, hits
the same Phase 7/8 archival hooks at the end.

This is genuinely net-new (no Researchmaxx analogue). Plausibly the
right shape, but the operator should ratify before Sprint 13.

### 3.5 [TRAINING-FACING] Verifiers environment rollout

`interfaces/research/environments/decomposer_env.py` is the first
verifier-shaped role wrapper. The other four orchestrate.py roles
plus an `rlm_env.py` that wraps the full RLM loop as one verifier
task should follow. These don't change runtime behavior; they enable
the Prime Intellect `prime-rl` training path the second paper
describes.

### 3.6 [SAFETY-FACING] REPL per-call timeout

Antiek's REPL captures exceptions but doesn't bound execution time.
RLM-generated code in principle could write an infinite loop in
Python. The 120s default Paper 2 ships with handles this. Add a
`signal.alarm`-based or `concurrent.futures`-based wrapper around
`RLMRepl.execute`.

---

## 4. Architectural fit

### 4.1 RLM is a substrate primitive, not a role replacement

The five role bridges remain the canonical Loop 1 chain. RLM enters
at three specific seams:

1. **Inside a role bridge** when input length exceeds context budget.
   The synthesizer bridge wraps its call in `rlm_loop` when the
   substrate block exceeds `SYNTHESIS_CONTEXT_BUDGET_TOKENS`.
2. **As an alternative bridge** for the document-wrestling case where
   the input is the document itself, not a pre-built context pack.
3. **As an alternative orchestrator** for `investigation_kind="rlm"`
   investigations that don't fit the 5-role chain.

In all three seams, the substrate decisions from architecture_notes
§2 hold unchanged:

- Every RLM iteration emits a typed event (new `rlm.iteration` action
  type proposed below).
- Every sub-LLM call inside the REPL flows through `substrate.dispatch`
  with cost tracking and policy_id stamping.
- Every tool call inside a sub-LLM flows through the substrate (the
  graph for `search_graph`, the network for `web_search` and
  `fetch_url`).

### 4.2 The four corners

| Corner | Pattern | Sprint | Status |
|---|---|---|---|
| Long-document wrestling | Wrestling bridge upgrades to RLM mode when doc > 64K tokens | 11 | net-new |
| Long-corpus synthesis | Synthesizer bridge wraps its call in `rlm_loop` when substrate block > budget | 12 | net-new |
| Open-ended exploration | New `rlm_orchestrator.py` parallel to `loop_one/orchestrator.py` | 13 | net-new |
| Verification redispatch | `skills/verification/rlm.py` (RLM-flavored, no REPL) | done | shipped Sprint 6 |

### 4.3 New typed events

The trajectory log needs to capture RLM execution at the right
granularity. Too coarse (one event per session) loses the per-iteration
sub-call structure that's the point of RLM. Too fine (one event per
Python statement) is noise.

Proposed: one event per RLM iteration (one round of LLM-writes-code →
REPL-executes → metadata-appended-to-history).

| Action type | Payload fields |
|---|---|
| `rlm.session_started` | session_id, kind (wrestling/synthesis/orchestrator), root_role, prompt_chars, max_iterations |
| `rlm.iteration` | session_id, iteration, code, stdout_chars, exception, answer_ready, sub_calls_made |
| `rlm.sub_call_dispatched` | session_id, iteration, sub_prompt_hash, sub_role, batch_index |
| `rlm.session_completed` | session_id, total_iterations, final_answer_chars, terminal_reason |
| `rlm.session_failed` | session_id, iteration, reason (timeout/max_iter/parse/exception), last_exception |

`session_id` links every RLM-internal event back to the originating
request. `parent_event_id` on each `rlm.iteration` points at the
session-started event so trajectory queries can reconstruct the full
RLM run as a tree.

Sub-LLM `dispatch.call` events get `parent_event_id` pointing at the
`rlm.sub_call_dispatched` event, which in turn points at the
`rlm.iteration` event, which points at `rlm.session_started`. The
full chain is queryable.

### 4.4 Cost attribution

Paper §4 observation 4: "the inference cost of RLMs remains
comparable to other methods... the median RLM run is cheaper than the
median base model run, but more expensive on average due to outlier
trajectories where the RLM struggles."

For Antiek's cost-tracking infrastructure (Sprint 1 dispatch + the
weekly_report), the implication is:

- Per-investigation cost should sum every `dispatch.call` event
  regardless of nesting depth. The existing aggregation in
  `runtime/weekly_report.py` does this correctly because it walks the
  trajectory file rather than filtering by role.
- Per-role cost breakdown should attribute sub-LLM calls to the root
  role, not the sub-role. So a synthesizer-as-RLM that fires 30
  flash-tier sub-calls reports as $X under "synthesizer" not as
  fragments under "note_taker" or wherever the sub-LLM was wired. The
  existing `target_role` field on `DispatchCallPayload` already
  supports this — set it to the root role for all sub-calls inside an
  RLM session.
- The outlier-trajectory failure mode the paper names is a real risk.
  Add a per-role-per-session cost cap: when the cumulative
  `cost_usd` in an RLM session exceeds the cap, the bridge
  short-circuits with a hedged answer rather than burning more
  budget. Default cap: 5× the role's median single-call cost (empirical
  threshold; tune after first 30 production runs).

### 4.5 Dispatch routing for the root vs sub-LLMs

The Pro/Flash split from architecture_notes §2.5 applies recursively.
For an RLM session:

- The **root** model handles meta-reasoning (decomposition, sub-call
  orchestration, final synthesis from sub-results). Pro tier (DeepSeek
  V4 Pro or Claude Opus 4.7).
- The **sub-LLMs** handle bulk processing (per-section summarization,
  per-chunk extraction, per-claim verification). Flash tier (DeepSeek
  V4 Flash or MiMo V2.5 Flash).

The paper confirms this is the cost-optimal split. For GPT-5
experiments they used "GPT-5-mini for the recursive LMs and GPT-5 for
the root LM" — explicit two-tier setup.

Antiek's `substrate/dispatch/config.yaml` already supports per-role
tier assignment. The wrinkle: the *same role* (e.g., synthesizer) now
calls itself recursively, with the root needing synthesis tier and
the sub-LLMs needing flash tier. Resolution: add an optional
`subllm_tier_override` field to the `dispatch` call signature; the
root passes its own tier as the override default. In `config.yaml`,
introduce a parallel `subllm_role_tiers` map that's consulted when an
RLM session dispatches a sub-LLM:

```yaml
subllm_role_tiers:
  synthesizer: flash   # sub-LLMs inside synthesizer-as-RLM run flash
  connector: flash
  decomposer: flash
  evidence_retriever: flash
  parameter_extractor: flash
```

All five reduce to flash tier when nested, because the root is
already handling the reasoning-heavy work and the sub-LLMs are doing
section-local processing.

---

## 5. Concrete integration plan

Five sprints. Each closeable in five days. Sprint 11 is load-bearing;
12–15 build on the same primitives without architectural surprises.

### 5.1 Sprint 11 — Long-document wrestling via RLM

**Goal:** the operator pastes a 200-page PDF, asks "what's the
load-bearing constraint on the methodology in chapter 4 given the
data assumptions in chapter 2?", and the wrestling bridge produces a
structured `DistillationDeliveredPayload` with claims grounded in
both chapters.

**Scope:**

- New constants: `RLM_REPL_PER_CALL_TIMEOUT_SECONDS = 120`,
  `RLM_DOC_RLM_THRESHOLD_TOKENS = 64_000`,
  `RLM_SESSION_COST_USD_CAP = 5.0` (cap per session; tune after
  production data).
- New action types: `rlm.session_started`,
  `rlm.iteration`, `rlm.sub_call_dispatched`,
  `rlm.session_completed`, `rlm.session_failed`. Five typed payloads.
- New bridge: `interfaces/research/api/rlm_wrestling.py`. Subscribes
  to `distillation.requested`. Routes to the existing wrestling
  bridge for documents below the threshold, to RLM mode for those
  above.
- RLM mode implementation:
  - Build a `FunctionRegistry` with `llm_query` (synthesis tier
    closure) + `llm_batch` (flash tier closure) + `search_graph` (the
    grounder's sub-LLM-with-tools).
  - Build an `RLMRepl` with `corpus={"prompt": full_document,
    "region_of_interest": region_text, "user_question": prompt}`.
  - Seed system prompt: "You are reading a long document. Your prompt
    is in the variable `prompt` (length: N chars). The user's
    question is in `user_question`. The selected region is in
    `region_of_interest`. Write Python code in the REPL to slice and
    re-call sub-LLMs as needed. Set `answer["content"]` to a JSON
    string matching the DistillationDelivered schema and
    `answer["ready"] = True` when complete."
  - `rlm_loop(repl, code_generator, max_iterations=8)`.
  - Per-iteration timeout wrapper around `repl.execute` using
    `concurrent.futures`.
  - Per-session cost cap: cumulative `dispatch.call.cost_usd` exceeds
    cap → force `answer["ready"] = True` with hedged content.
- Emit `distillation.delivered` from the parsed `answer["content"]`,
  identical schema to the current bridge so the React surface needs
  zero changes.

**Tests:**

- Stub LLM that returns canned RLM code → assert the bridge produces
  the expected event chain (session_started → 3 iterations →
  completed → distillation.delivered).
- Stub that returns code with an infinite loop → assert timeout fires
  and `rlm.session_failed` lands.
- Stub that runs up cost > cap → assert session terminates with
  hedged answer.
- Stub that calls `llm_batch` with 5 prompts → assert 5
  `dispatch.call` events fire with correct `parent_event_id`.
- Document below threshold → assert RLM mode is NOT entered (falls
  through to existing wrestling bridge).

**Effort estimate:** ~600 LOC across the bridge + payloads +
constants + ~25 tests.

### 5.2 Sprint 12 — Long-corpus synthesis in Loop 1

**Goal:** a Loop 1 investigation that produces a substrate block
larger than 256K tokens (many sub-questions, many parameters, many
graph paths) still archives a coherent synthesis.

**Scope:**

- Synthesizer bridge gains a length check. If the rendered substrate
  block exceeds `SYNTHESIS_CONTEXT_BUDGET_TOKENS`, route through an
  RLM execution.
- RLM mode for synthesizer:
  - `prompt` variable = full substrate block.
  - Sub-LLMs = per-sub-question synthesizer calls at flash tier.
  - Root LLM at synthesis tier composes the final thesis from the
    per-sub-question summaries.
  - The constraint loop machinery (Sprint 7 Day 3) still wraps the
    outer call. Revisions feed the RLM REPL fresh `answer` state and
    re-run.
- No new bridge — extends the existing synthesizer bridge in
  `interfaces/research/api/synthesizer.py`.
- Re-use the `RLMRepl` + `rlm_loop` + cost cap from Sprint 11.

**Tests:**

- Stub substrate block at 300K tokens → assert RLM mode is entered,
  thesis lands, constraint loop runs around the RLM call (not inside
  it).
- Constraint violation after RLM completes → assert constraint loop
  re-invokes synthesizer-as-RLM with revision context.

**Effort estimate:** ~250 LOC; reuses Sprint 11 primitives.

### 5.3 Sprint 13 — Open-ended RLM orchestration

**Goal:** the operator posts an open-ended question (e.g., "explore
this corpus and tell me what's worth reading") and gets an
investigation that doesn't force the 9-phase chain.

**Scope:**

- New `InvestigationKind` Literal on
  `InvestigationStartRequestedPayload`: `"loop_one" | "rlm"`. Default
  `"loop_one"` — backward compatible.
- New module `orchestration/loop_one/rlm_orchestrator.py`. Mirrors
  the shape of the existing event-driven orchestrator but uses an
  RLM root instead of the role chain.
- The RLM root has access to:
  - `llm_batch` for parallel decomposition.
  - `search_graph` for retrieval against the investigation's graph.
  - `execute_dag` from `rlm_dag.py` for structured sub-task planning.
- Phase 7 (archive) and Phase 8 (Phase 8 distillation + auto_patch)
  still fire on the RLM root's terminal answer. Same archival shape;
  the difference is upstream (no phase 1–6 events; instead, RLM
  iteration events).
- Postcondition adjustments in `orchestration/phase_runner/postconditions.py`:
  phases 1–5 either skip or pass trivially for RLM-kind investigations.

**Tests:**

- `investigation_kind="rlm"` cold question → assert RLM session runs
  end-to-end, Phase 7 + 8 land, `investigation.completed` fires.
- Both kinds run concurrently → assert per-investigation coordinator
  state isolation holds.

**Effort estimate:** ~500 LOC; the trickiest part is phase_runner
postcondition adjustments.

### 5.4 Sprint 14 — Verifiers environment rollout

**Goal:** the other four orchestrate.py roles plus a full-RLM env
are exposed as `verifiers.Environment`-shaped scaffolds so the Prime
Intellect `prime-rl` training path becomes usable.

**Scope:**

- `interfaces/research/environments/synthesizer_env.py`
- `interfaces/research/environments/connector_env.py`
- `interfaces/research/environments/evidence_retriever_env.py`
- `interfaces/research/environments/parameter_extractor_env.py`
- `interfaces/research/environments/rlm_env.py` — wraps the full RLM
  loop as one verifier task; uses the existing 4 RLM-flavored
  environments from Paper 2 (DeepDive, math-python, Oolong,
  verbatim-copy) as reference shapes.

Each environment ships with:
- `Task` / `Rollout` / `Reward` dataclasses mirroring
  `verifiers.Environment`.
- 3–5 verifiable rubrics from `skills/verification/rubric.py`.
- An extension hook for judged rubrics.
- Tests that inject a deterministic stub provider so the env runs
  without sentence-transformers.

**Effort estimate:** ~400 LOC per environment × 5 = ~2,000 LOC.
Closeable in one sprint because the pattern is grooved (decomposer_env
established it Sprint 9 Day 5).

### 5.5 Sprint 15 — Training trajectory harvesting

**Goal:** the operator can export production trajectories in a format
`prime-rl` consumes, filtered by outcome quality.

**Scope:**

- New CLI: `python -m tools.training.harvest --since DATE
  --quality-threshold 0.7 --output trajectories.jsonl`.
- Quality filter: for each completed investigation, compute the
  composite of (constraint-pass rate, synthesis-archived flag,
  backtest outcome correlation when available).
- Output format: verifiers-compatible JSONL — one trajectory per line
  with `{task, rollout, reward}` matching the env shapes from Sprint
  14.

**Effort estimate:** ~300 LOC + tests.

---

## 6. Design decisions to ratify before Sprint 11

Six choices this spec has made provisionally. The operator should
confirm or counter before Sprint 11 starts.

### 6.1 RLM-as-bridge vs RLM-as-service

**Proposal:** RLM execution lives inside the bridge handler as a
closure over the dispatch router. Same pattern as `wrestling.py`,
`grounding.py`, etc.

**Alternative:** RLM execution as a separate service (`rlm.py`) that
bridges call. More testable, more verbose.

**Recommendation:** keep it in the bridge. The bridge IS the RLM
execution context — separating them buys nothing.

### 6.2 Sub-LLM cost attribution

**Proposal:** all sub-LLM dispatch calls inside an RLM session set
`target_role` to the root role. So a synthesizer-as-RLM that fires 30
flash-tier sub-calls reports as 30 calls under "synthesizer" with
flash-tier costs.

**Alternative:** attribute by sub-role (whatever role the sub-LLM is
configured for). More granular but loses the "this synthesis cost
$X" simplicity.

**Recommendation:** attribute to root role. Per-investigation cost
becomes legible. The trajectory still carries the full nested
structure via `parent_event_id` for forensic queries.

### 6.3 Per-session cost cap

**Proposal:** `RLM_SESSION_COST_USD_CAP = 5.0`. When cumulative
sub-call cost in a session exceeds this, force `answer["ready"] = True`
with hedged content.

**Alternative:** no cap; let outlier trajectories run.

**Recommendation:** cap. Paper §4 observation 4 names the outlier-cost
failure mode explicitly. 5.0 is a guess; tune after first 30
production runs.

### 6.4 The Pro/Flash split for sub-LLMs

**Proposal:** `subllm_role_tiers` map in `config.yaml`. All five
orchestrate.py roles reduce to flash tier when nested. Root runs at
the role's configured tier.

**Alternative:** sub-LLMs inherit the parent role's tier verbatim.
Simpler config, more expensive.

**Recommendation:** the map. The paper is explicit that this is the
cost-optimal split. The config-edit-not-code-edit discipline already
in place handles it cleanly.

### 6.5 RLM trajectory event granularity

**Proposal:** one event per iteration, plus dispatch events for
sub-LLM calls. So a 5-iteration session with 3 sub-calls per
iteration emits ~20 events.

**Alternative:** one event per session. Loses the per-iteration
structure that's the point.

**Recommendation:** per-iteration. The trajectory log can compact
later if volume becomes a problem; granularity can't be reconstructed.

### 6.6 Wrestling threshold

**Proposal:** `RLM_DOC_RLM_THRESHOLD_TOKENS = 64_000`. Below this,
fall through to the existing wrestling bridge. Above, RLM mode.

**Alternative:** always use RLM mode (more uniform, more expensive
for short docs). Or higher threshold (128K, 256K — saves on RLM
overhead for medium-length docs).

**Recommendation:** 64K. Short enough that the existing bridge
performs near-optimally (single dispatch, no RLM loop overhead);
long enough that anything above triggers genuine context-rot
concerns.

---

## 7. Validation criteria

The integration is complete when these properties hold:

1. **Long-document wrestling works.** A 500-page PDF pasted to the
   reading surface, with a cross-chapter question, produces a
   structured `DistillationDeliveredPayload` with `claims` whose
   `attribution_region_ids` reference regions from multiple chapters.
   The bridge runs in under 90 seconds on flash-tier sub-calls;
   total cost under $0.50 for the document.

2. **Long-corpus synthesis works.** A Loop 1 investigation with 8
   sub-questions, each yielding 10+ supporting claims, archives a
   coherent thesis. The synthesizer bridge enters RLM mode; the
   constraint loop wraps the RLM call (not the other way around);
   total synthesis tokens > 300K, cost in line with the existing
   non-RLM path (within 30%).

3. **Open-ended RLM orchestration works.** An
   `investigation_kind="rlm"` question produces an
   `investigation.completed` event with a populated `master_md_path`
   and at least one `domains_patched` entry. Phase 7 + 8 trigger
   normally; the trajectory shows RLM iteration events instead of
   the 9-phase event chain.

4. **Cost discipline holds.** Per-investigation cost reported by
   `runtime/weekly_report.py` is correct (sums all nested dispatch
   calls). Per-role cost attribution shows the synthesis tier
   dominating root costs and flash tier dominating sub-LLM volume —
   the paper's empirical split.

5. **Tool isolation holds.** Every tool registration in the codebase
   attaches to a `SubLLMWithTools` instance; no root RLM has tools.
   A static check in `tests/` enforces this by walking the bridge
   modules and asserting no `RLMRepl` registry contains tools.

6. **Sub-LLM cost cap works.** A deliberately runaway session
   terminates with a hedged answer when cumulative dispatch cost
   exceeds `RLM_SESSION_COST_USD_CAP`. The session emits
   `rlm.session_completed` with a `terminal_reason: cost_cap` field.

7. **Trajectories are queryable.** For any RLM session,
   `parent_event_id` chains let a trajectory walker reconstruct the
   full call tree: session → iteration → sub_call_dispatched →
   dispatch.call. Tests demonstrate this reconstruction round-trip.

8. **Verifiers environments work.** All five role envs +
   `rlm_env.py` ship with passing tests. At least one env runs an
   end-to-end task against a stub provider and produces a non-trivial
   `Reward`.

9. **Training harvest produces a usable JSONL.** Running
   `tools.training.harvest` against accumulated trajectory data
   produces a verifiers-compatible JSONL the operator can feed to
   `prime-rl` without further transformation.

When all nine hold, RLM is a first-class substrate primitive in
Antiek, not just a collection of migrated Researchmaxx files.

---

## 8. What this spec does NOT cover

For explicitness:

- **Local RLM training.** Antiek does no training. Trajectory
  harvesting (Sprint 15) is the interface to external training
  infrastructure (Prime Intellect `prime-rl`). Decisions about which
  base model to fine-tune, what hardware to use, and when to deploy
  a custom RLM-Antiek model are operator-side.
- **DeepBlu interview surface.** Out of scope; deferred per
  consume-first decision Sprint 1. When DeepBlu lands, RLM is the
  obvious primitive for the AI interviewer's between-turn
  graph-querying (Paper 2: "the AI interviewer is superhuman
  precisely because it queries the project's graph between turns").
  That integration gets its own spec.
- **Cross-language RLM (RLM in TypeScript for the reading UI).** The
  reading UI emits typed events into the substrate; the substrate
  runs RLM in Python. Polyglot boundary unchanged from
  architecture_notes §11.
- **Local sandbox isolation.** Sprint 11 ships the AST-validated
  in-process sandbox already in `rlm_repl.py`. Process-level
  isolation (Prime Intellect Sandboxes equivalent) is a Sprint 16+
  hardening that depends on whether RLM is ever exposed to
  non-operator inputs. Not gated.

---

## 9. Why this spec, why now

The honest framing: Researchmaxx had `rlm_repl.py`, `rlm_tools.py`,
`rlm_dag.py`, and `rlm_v4_validation.py` from the start. Antiek's
Sprint 9 migration ported them faithfully. But porting != integrating.
The four modules sit as standalone primitives — usable from a CLI,
not wired into any of the bridges that handle real operator-facing
work.

This spec is the missing wiring document. It says: the wrestling
bridge needs RLM. The synthesizer bridge needs RLM. Phase 8 long-doc
distillation needs RLM. The operator's Sprint 1 vision named all
three, and the substrate is now mature enough that each integration
is a 1-sprint surgical procedure rather than an architectural
overhaul.

The MIT paper's contribution to this spec is the formal contract —
the four properties §1.2 enumerates, the cost calculus §4.4 cites.
The Prime Intellect paper's contribution is the productization
recipe — `answer["ready"]` diffusion, `llm_batch` parallelism, the
60–120s REPL timeout, the verifiers environment shape, and the
empirical observation that fine-tuning even an 8B model on 1,000
unrelated-domain RLM trajectories produces a 28% performance lift.

Both are correct about what RLM is. Antiek's job is to make it the
default scaffold for long-context work, while keeping the role chain
as the canonical short-context Loop 1 path. The two coexist; the
operator chooses which one runs based on input characteristics
(document length, question shape, investigation kind).

Sprint 11 starts when this spec is ratified.
