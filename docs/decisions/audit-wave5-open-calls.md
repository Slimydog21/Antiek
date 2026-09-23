# Audit wave 5: what the repairs leave open

**Date:** 2026-09-23
**Status:** PROPOSED. Five operator calls, each with a recommendation, plus the routing and pre-existing findings this wave surfaced. None of the calls is executed.
**Owner:** Antiek audit wave 5. It was an executing-refuter audit, at main `95093e84b` with 66 agents, of eight surfaces that waves 2 to 4 did not cover: the loop-one orchestrator, remote-exec fan-out, ads and attribution money, the provenance chain, export and artifacts, agent-memory MCP, interview and Speak, and the reader and workspace frontend. It confirmed 24 findings (10 of them latent), refuted 5 and left 10 low-severity ones unverified.
**Builds on:** the `fix/audit-wave5` stack. It covers W01–W07, W10–W13, W19–W24, the `/export/my-graph` secret columns, one cross-cluster integration fix and a docs correction. Every repair has a test that was red before its fix, a production-file revert that turns it red again, an independent executing review, and a different-lineage review (codex gpt-6-sol). That last review rejected round 1 with 9 defects, which are being fixed with codex itself as the reviewer. Findings W08 and W09 (frame-attention accrual) and W14–W18 (agent-memory MCP) were routed to the lanes that own those files.

---

## Operator calls

### 1. Does an unparseable model answer end a research as "completed"?

Decision H2.5 (`deep-research-terminal-contract.md`) ratifies it: a synthesizer that answered but could not be parsed, even after self-repair, ends completed with `insufficient_evidence`. Wave 5 did not overturn that. It separated the case H2.5 never covered, a provider outage where no model answered at all. That case now ends failed, because a typed `role_outcome=dispatch_failed` fails phases 2, 3, 4 and 6. Two choices remain yours.

The first is whether a parse failure should also count as a failure rather than "underdetermined". The second concerns partial outages: any `dispatch_failed` delivery now fails its phase, including 1 of N Phase 2 sub-questions, and the alternative would tolerate k of N.

**Recommendation:** keep H2.5 for parse failures, because the model did engage. Keep failing closed on any outage until k-of-N has a stated k and a test.

### 2. How does the UI show a stopped or budget-halted research?

The backend readers now agree: stopped, cancelled and budget-halted all read `stopped`. The reader hook `apps/reading/src/hooks/useInvestigation.ts` has no `stopped` state and still collapses it. The API type now includes `stopped`, so nothing polls forever, but the copy and state are a design call.

**Recommendation:** a distinct "Stopped by you" state with the leaves' outcomes. It should not reuse "completed" or "failed".

### 3. Reconciling runs killed without a graceful cancel

A graceful cancel now writes a failed terminal, both for Loop One and the cascade tail. A hard kill (SIGKILL, OOM) still leaves a run reading `in_progress` forever. A startup sweep would need to know which process owns a run, because `antiek-continuous-research` has its own runs in flight.

**Recommendation:** a lease row per running investigation (owner process and heartbeat), with a startup sweep that fails only runs whose lease expired.

### 4. A "stop the whole session" control, and whether an empty gather counts as done

Stopping every leaf now prevents the paid synthesis tail, and the session parent ends with an honest terminal. If one leaf finished with evidence before you stopped the others, the tail still runs over that evidence; there is no session-wide stop. Separately, a session whose gather found nothing now fails at phase 6 instead of paying for an `insufficient_evidence` synthesis. That follows the ratified session-evidence-pack decision, which the wave-5 provenance fix amended with its reasoning.

**Recommendation:** add a session-level stop that cancels a pending tail, and keep empty-gather sessions failed rather than "complete".

### 5. Speak projects with no named subject

A project created without a `subject_ref` can no longer publish publicly. There is nowhere to record subject consent, and no route sets the subject after creation. The options are (a) require `subject_ref` when `publish_intent` is `will_be_public`, or (b) add a project-level "non-identifiable or deceased" rationale for when no subject is named.

**Recommendation:** (a). Refusing at creation is clearer than discovering at publish time.

Related export call: merging a book's own derived insights back into that same non-servable book (`/research/artifacts/source-merge/*`) now merges cite-only notices. Whether the owner may merge full text back needs the owner-privileged read path, and the fix fails closed until you decide.

---

## Routed to other lanes

| Finding | Owner | State (2026-09-23) |
|---|---|---|
| W08 frame-attention re-mints a window's revenue on every flush (high, latent) | SPR-08 lane | Fixed on `fix/w5-ads-accrual-20260923` @ `1349e3356`, codex ACCEPT, queued in the merge train |
| W09 dwell cap skipped at zero dwell (medium, latent) | SPR-08 lane | Same branch |
| W14–W18 + `cite_source` (agent-memory MCP) | #3403 lane | Fixed on `fix/w5-mcp-hardening-20260923` @ `f6c8814e5`, merging after #3403. The lane's critic also reproduced and fixed three pre-existing MCP defects on the #3403 base, each mutation-tested: a private-note resource that took `user_id` from the URI, so any caller could read another user's note (high); `search_personal` serving a taken-down book's body (high); and an untrusted-content envelope that untrusted text could close early (low). Still open: `record_attribution` does not check `book_assets.taken_down` (medium, matching the HTTP path). W16 is a hash pin rather than a key signature, which needs an operator-held signing secret: **operator call**. |

## Pre-existing on main, surfaced by this wave

- **Staging-merge file-handle conflict.** `tools/merge_staging.py` raises `BinderException: Unique file handle conflict` when the corpus runner merges in-process while a warm writer is still parked (`run_corpus_ingest.py`, `db_lock.py`). Found by the codex critic on #3415 and filed by the merge-train owner. It is not caused by either stack.
- **A required-shard timing flake.** `test_loop_one_happy_path_emits_completed` took 21.5 s of a 30 s budget on main because `roles/decomposer/paraphrase._load_default_embedder` ignored `ANTIEK_EMBEDDING_PROVIDER` and always loaded MiniLM. **Fixed in this stack** (`8110fc5da`): the test now runs in 1.1 s.
- **Deploy starvation.** Deploy jobs share the 20-job runner pool with PR CI, and GitHub has no job priority. Prod sat two hours behind main this afternoon (see the wave-4 record for the gated-SHA fix). The structural answer, such as a self-hosted runner for the deploy job, is an infrastructure call.
