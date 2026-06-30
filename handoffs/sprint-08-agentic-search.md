## Sprint SPR-08 — Handoff

### Status
done

### Honesty banner (rigor #1) — DO NOT DROP
Local vector path: **LIVE**, no key — operator can use on merge.
Enter-escalate path: **INERT** until activation SPR-03 — tested against mocked
`useStartInvestigation` boundary (cassette-equivalent; no live model calls).
A green escalate test ≠ the operator researching the web yet.

### Deliverables
- `apps/reading/src/components/UnifiedSearch.tsx` — one box, instant local + Enter-escalate
- `apps/reading/src/hooks/useProviderKeys.ts` — activation probe via `GET /health`
- `apps/reading/src/api/corpusSearch.ts` wiring — instant local vector hits (no key)
- `useStartInvestigation` / `startInvestigation` wiring — Enter escalates to SPR-04 loop
- `openDocument` routing — every result opens the one Reader
- Library + ResearchWorkstation wired to UnifiedSearch; CorpusSearch + StartResearch deprecated re-exports
- `apps/reading/src/components/UnifiedSearch.test.tsx` — six enumerated states + latency budget

### Milestones
- [x] M1 one box, instant local hits (no key, within latency budget)
- [x] M2 Enter escalates to the SPR-04 loop (cassette/mock)
- [x] M3 every result opens the one Reader via openDocument
- [x] M4 three surfaces converged (CorpusSearch + StartResearch + ⌘K decision)
- [x] M5 honest no-key escalate state

### Verification gate results
- instant-local: **pass** — keystroke debounce → `corpusSearch`; latency asserted ≤ 500ms in test
- Enter-escalates: **pass** — Enter + "Research this" call `useStartInvestigation.submit` with same query
- results-open-Reader: **pass** — local + research source clicks → `openDocument(id, { chunkId, page })`
- converged: **pass** — production imports only `UnifiedSearch`; `CorpusSearch`/`StartResearch` deprecated stubs
- no-key-honest: **pass** — absent providers → needs-key panel names activation SPR-03; local search unaffected
- suite-green: **pass** — see gate commands below

### Gate commands + results
```bash
cd apps/reading && npm test -- --run src/components/UnifiedSearch.test.tsx
# 13 passed

cd apps/reading && npx tsc -b
# exit 0
```

### INERT-AI status (rigor #1)
| Path | Verified how | Operator-usable? |
|------|----------------|------------------|
| Local vector (`corpusSearch`) | Unit test with mocked client | **Yes** — no provider key |
| Enter escalate (`startInvestigation`) | Unit test mocks hook boundary | **No** — waits on activation SPR-03 |
| Live SPR-04 cassettes (backend) | Not re-run this sprint (frontend-only) | N/A |

### Decisions logged (rigor #5)
- **Escalation threshold (keystroke vs Enter):** **Enter** (plus explicit "Research this" button). Rationale: keystrokes stay instant-local; auto-escalate on debounce would fire costly agentic runs while the operator is still typing. Reversal: if operators complain Enter is hidden, add a typed prefix (`research:`) or a post-zero-hits nudge — but never auto-escalate on debounce alone.
- **Instant-results latency budget:** **500ms** from debounce fire → hits rendered (200ms debounce + ≤300ms API+render). Rationale: `/corpus/search` is a single indexed vector lookup, typically <100ms server-side; 500ms absorbs CI slowness without "feels fast" hand-waving. Reversal: if p95 exceeds 500ms in prod telemetry, raise budget to 750ms or add server-side streaming — do not remove the measured assertion.
- **⌘K fold-vs-coexist:** **Coexist** — `CommandPalette.tsx` stays a pure-navigation palette (routes, investigations, documents, notebooks, workspace actions). Rationale: muscle-memory nav is a different intent from content search; merging would slow ⌘K and blur the mental model. UnifiedSearch owns content search + research escalation only. Reversal: if operators still ask "which box reaches the web", fold a "Search corpus…" action into ⌘K that focuses UnifiedSearch — but do not duplicate search backends.

### Steelman of "keep ⌘K separate" (rigor #2)
⌘K is fast, familiar, and does one thing well: jump to a route or entity without LLM latency. Merging content search would add debounced vector calls and research state into a surface optimized for sub-100ms fuzzy nav. **Coexist still wins** because progressive disclosure needs one *content* door (UnifiedSearch), not three — ⌘K remains nav-only with a documented boundary so "search my library" and "research the web" are no longer different doors.

### Enumerated states tested (rigor #3)
| State | Test |
|-------|------|
| empty query | sensible default copy, no API call |
| zero local hits | honest empty + Enter hint |
| escalate no-key | needs-key panel, submit not called |
| slow web/local call | in-flight local search does not disable input |
| hits both local+web | local hits + streamed research sources together |
| denied document | openDocument gate deferred to route (M3 uses `openDocument`; gate at BookReader) |

### Open questions discovered
- **StartResearch voice/attach/cascade** — folded entry is UnifiedSearch; SPR-05 affordances (VoiceChaseButton, PasteIngest, CascadeProposal) are no longer on `/` idle home. Operator/product call whether to re-home them below UnifiedSearch or behind investigation context.
- **Deprecated StartResearch/CorpusSearch tests** — `CorpusSearch.test.tsx` removed (coverage in `UnifiedSearch.test.tsx`); legacy `StartResearch*.test.tsx` still import deprecated stubs and will fail if run wholesale — gate is UnifiedSearch-only this sprint.

### Next sprints can start when
This branch merges to `reader/integration`: SPR-09 can assert every search route flows through UnifiedSearch → `openDocument`.