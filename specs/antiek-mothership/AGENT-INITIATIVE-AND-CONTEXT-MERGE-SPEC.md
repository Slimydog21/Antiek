# D7/D8 — Agent initiative and agent context merge

Status: PROPOSED (Kimi design lane, 2026-10-08). Awaits operator ratification like C1–C5.
Depends on: #3752 (SPR-06 contracts), #3756 (SPR-07 agent pane), #3758 (SPR-10 monitoring), sprint-B backend contracts.
Origin: operator goal 2026-10-07/08 — "I just want to talk to one agent who is in control"; "different agents appear as the themes crystalize and the various AI sessions merge their contexts"; "subagents exist under main agents and they merge eventually"; "there is also a world where I want to start the discussion with an agent and ask it what I should read / what is missing in my research / what is weak in my writing, then it opens the second pane."

Both asks are real and currently unmodeled:

1. **Agent initiative** — every pane-open path on #3756's head is user-gestured (`apps/reading/src/workspace/agent/openAgentPane.ts:66-110`). No agent can open or badge its own pane. The operator's "the agent opens the second pane for me" half does not exist.
2. **Context merge** — `AgentNode` (`apps/reading/src/workspace/contracts/tree.ts`) has no merged-from representation. `agentFingerprint` (`treeStore.ts:32-38`) cannot see a merge, so the identity-reuse store would silently keep two stale nodes. The operator's "contexts merge manually or automatically" does not exist.

This spec adds both as additive extensions of the frozen SPR-06/SPR-07 surfaces. Nothing here rewrites them; every change is a new optional field, a new reply action, or a new store action beside the frozen ones.

---

## D7 — Agent initiative: the agent may ask for attention, never take it

**Decision.** An agent run may emit an *initiative* — a request to open or badge its pane — but the initiative is **badge-first, focus-never**. The agent earns attention through the monitoring surface (#3758's five states and attention order); it never moves the user's cursor, never steals pane focus, never opens a pane over reading.

### D7.1 The initiative object

A run's reply transport (agentTransport.ts, SPR-B successor) may carry:

```ts
interface AgentInitiative {
  kind: "open_pane" | "badge";
  /** One of the canned intents the operator named, or free. */
  intent: "what_to_read" | "missing_research" | "weak_writing" | "finding" | "question" | "done";
  /** One sentence, rendered verbatim in the badge/toast. Provenance-labelled like any AI text. */
  headline: string;
  /** Deep link payload: same vocabulary as paneHash (`p:<projectId>`, `x:<n>`) plus optional DocumentAnchor. */
  target: { agentId: string; anchor?: DocumentAnchor };
}
```

Rules:

- **Badge**: the agent's tab and its tree node (#3752) show the attention badge; the monitor (#3758) orders it by the existing attention order. No toast unless the run *transitions into* blocked/needs-you (the existing transition-only toast rule).
- **open_pane**: honored only when (a) no composer has unsent text, (b) the reading focus is idle (no pinned selection, no IME open), and (c) the same initiative has not been dismissed in this session. Otherwise it degrades to badge. This is the "it opens the second pane" case — it opens *beside* the user, never *over* them.
- The user gesture equivalents stay exactly as on #3756: `prefix+a` / `ctrl+alt+a`, composer chips, deep links.

### D7.2 Consent and provenance

- Every initiative is recorded on the run's thread (agentThreadStore) with `origin: "agent"`, so the human-facing companion document can show *why* a pane appeared. AI-initiated UI is AI output: it carries the same "AI reply" labelling discipline as #3756's thread.
- Dismissal is remembered per run per session (`dismissedInitiatives` in agentPaneStore, session-scoped like drafts). A dismissed initiative never re-fires; a *new* initiative (different intent or headline) may.
- The canned trio the operator named — "what should I read", "what is missing in my research", "what is weak in my writing" — are first-class intents with fixed copy, not free text, so the monitor can group them.

### D7.3 Where it lands in the cockpit

- `openAgentPane` gains one optional parameter `via: "user" | "initiative"` (default `"user"`); initiative opens are identical except they pass through the D7.1 degrade rules first. One open path stays one open path.
- The right-pane agent tab is the same companion tab (#3756); initiative does not create a new pane kind, a new id space, or a new store.

## D8 — Agent context merge: many threads, one agent in control

**Decision.** Agents merge as **first-class, reversible, provenance-preserving events**. A merge never deletes a thread: participants keep their full transcripts and become `merged_into` pointers; the survivor holds the union of contexts and a `mergedFrom` list. The user talks to one agent; the evidence base keeps every contributor.

### D8.1 Data model (additive on SPR-06 contracts)

```ts
// contracts/tree.ts — AgentNode gains:
interface AgentNode {
  // …frozen fields unchanged…
  /** Ids of agents merged INTO this one. Absent = never absorbed anyone. */
  mergedFrom?: readonly string[];
  /** Set on a participant after merge: the survivor's id. The node stays in
   *  the tree (greyed, "merged") so history, badges and citations resolve. */
  mergedInto?: string;
}
```

- `agentFingerprint` (treeStore.ts:32-38) must include `mergedFrom`/`mergedInto` — otherwise the identity-reuse store serves stale nodes after a merge. This is a one-line-per-field change with a fingerprint test.
- Merge of two agents in different projects is a **cross-project merge**: the survivor's scope becomes `cross-project` (the `x:<n>` id space already exists), and both projects' nodes link to it. Scope provenance rules from CONTRACTS.md §2 apply unchanged.

### D8.2 Merge paths

- **Manual**: the user selects two agent tabs (switcher multi-select or tree panel) → "Merge contexts" → confirmation names the survivor (default: the older run; the user may flip). Provenance: the merge event records `initiated_by: "user"`.
- **Automatic**: the backend (SPR-B, ffx-nav-agent-bridge) may *propose* a merge when embeddings/themes converge — but a proposal is an **initiative (D7.1), never an action**. The user confirms or dismisses. No silent merge, ever: merging rewrites what "the agent" knows, and silent context mutation is exactly the blurred line the operator's provenance ask forbids.
- **Split (undo)**: a merged agent can be split back along `mergedFrom` lines. The survivor's transcript keeps merged turns labelled with their contributor (`via: <agentId>`), so a split is lossless re-partitioning, not reconstruction.

### D8.3 The one-agent-in-control surface

- After merges, a project typically has one *lead* agent: the survivor of its merges. The tree panel and switcher render the lead first; other agents are its absorbed threads, expandable.
- "Talk to one agent who is in control" = the lead agent answers using the union of merged contexts; when an answer leans on an absorbed thread, the thread citation names that thread (agent-facing metadata always; human-facing when the response chooses quote style — the existing provenance contract).

### D8.4 Backend wire needs (SPR-B, coordinated, not duplicated here)

Already listed in the review synthesis as backend-owned; restated so sprint-B's contract page has one checklist:

1. `project_id` on the thought-partner/agent wire (scope enforced server-side — today client-only, agentTransport.ts:37-62).
2. A run-status push channel so `blocked`/needs-you is reachable in production (today DEV-only seam, agentStatus.ts:114).
3. Merge endpoints: propose / confirm / split, with `initiated_by` and full participant preservation.
4. Handoff F3: the `open_writer` reply action (AgentReplyActions.tsx disabled stub) so "what is weak in my writing" can land the user in Write mode with the weak spans anchored.

## Acceptance (what 100/100 means for D7/D8)

- [ ] An agent-initiated `open_pane` opens the companion tab beside the user's work with focus unchanged; axe-core + keyboard-only e2e prove focus stayed put; a dismissed initiative never re-fires (property test over initiative sequences).
- [ ] Badge-only initiatives flow through #3758's attention order with zero new window listeners (the census test pattern).
- [ ] A manual merge of two agents with real transcripts preserves every turn, labels contributors, updates the tree via `publishTree` only, and the fingerprint change re-renders exactly the affected subtree (identity-reuse test).
- [ ] Split after merge restores both threads byte-identical (round-trip property test).
- [ ] Every merge/initiative event appears in the human-facing companion document and the agent-facing evidence base with provenance intact.
- [ ] No silent mutations: any automatic proposal requires user confirmation; the UI copy never calls a pre-backend node "Sub-project" (rigor #1 holds).

## Non-goals

- No changes to the frozen SPR-06 opener vocabulary beyond the already-recorded F1(c) extension point.
- No automatic merging without confirmation; no focus theft; no new pane kinds, id spaces, or stores.
- Backend endpoint design itself — sprint-B owns the wire; this spec owns the client semantics and the provenance rules the wire must carry.
