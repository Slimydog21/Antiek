# Agent execution templates

Copy-paste blocks for ANT-H2V and any Antiek agent session. **Do not delete headings** in the Handoff Packet — use `N/A — reason` when a section does not apply.

Protocol: `docs/agent-execution/HARD_TO_VARY.md`

---

## Env Card

Paste at the top of every handoff and before canonical verify (Phase D).

```markdown
## Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | YYYY-MM-DD |
| Repo root (`pwd`) | `/absolute/path/to/Antiek` |
| Branch | `caffen/SPR-01` |
| Commit SHA | `abcdef1` |
| Python | `/absolute/path/to/Antiek/.venv/bin/python` |
| Python version | `3.12.x` |
| LLM contacted this session | `yes \| no` |
| Network required for gates | `yes \| no` |

**Sanity (run before gates):**
```bash
pwd
.venv/bin/python -V
which .venv/bin/python
```
```

---

## Failure Dossier

Phase A — contract lock. Ground in source lines; state whether an LLM ran on the failure path.

```markdown
## Failure Dossier

**Reported symptom:**
(e.g. Reading UI “no result” on auto-decompose)

**LLM contacted on failure path:** `yes \| no`
(Pre-network TypeError ⇒ typically **no**)

### Signatures (from source, not memory)

| Callable | Location | Required kwargs |
|----------|----------|-----------------|
| `render_full_prompt` | `roles/decomposer/prompt.py:123` | `investigation_id`, `question`, `context` (keyword-only) |
| `dispatch` | `substrate/dispatch/router.py:301` | `investigation_id` (keyword-only) |
| `DispatchDecomposer.decompose` | `roles/cascade_planner/planner.py:57` | (adapter — must satisfy above) |

### Numbered failure chain

1. **Trigger:** `POST /research/plans` without `sub_questions[]` — `file:line`
2. **Branch:** `_decompose()` — `file:line`
3. **Adapter:** `DispatchDecomposer.decompose` — `roles/cascade_planner/planner.py:57-69`
4. **Exception:** `TypeError` — (paste message: missing keyword `investigation_id` / unexpected positional)
5. **HTTP:** `500` — `file:line`
6. **UI:** empty / error state — (operator-visible)

### Old vs new call pattern (if applicable)

| Call site | Before (broken) | After (contract-correct) |
|-----------|-----------------|---------------------------|
| `render_full_prompt` | `render_full_prompt(question)` | `render_full_prompt(investigation_id=…, question=…, context=…)` |
| `dispatch` | `dispatch(prompt, role="decomposer")` | `dispatch(prompt, role="decomposer", investigation_id=…)` |

### Repro gate

```bash
cd <repo-root>
.venv/bin/python scripts/repro_cascade_decompose_contract.py
```

**Result:** exit `0` | `non-zero` — (paste last line, e.g. `REPRO_OK`)

### What repro does NOT prove

- Live provider health
- Non-cascade entry points (see Scope Map)
```

---

## Scope Map

Phase B — bounded scope before “platform OK” or sprint closure.

```markdown
## Scope Map

**Sprint / investigation ID:** ANT-H2V SPR-XX
**In-scope for this session:** (one sentence)

### Decompose entry points

| ID | Path / trigger | Production hook | Test status | Evidence | Live LLM |
|----|------------------|-----------------|-------------|----------|----------|
| E1 | POST `/research/plans` omit `sub_questions` | `DispatchDecomposer` | `untested` | — | `required` for operator card |
| E2 | POST `/research/plans` with `sub_questions` | fixed decomposer | `tested` | `tests/…:line` | `no` |
| E3 | Loop1 investigations bus | `make_decomposer_handler` | `untested` | `file:line` | `yes` |
| E4 | Gap / note planners | (name module) | `untested` | — | `unknown` |

**Test status legend:** `tested` | `untested` | `live-LLM-required`

### Explicitly out of scope (this session)

- (bullet)
- (bullet)

### Temptations resisted

- (what you did NOT do and why)
```

---

## Handoff Packet

Matches ANT-H2V htmlspec sprint footer (`sprint-01-agent-protocol.html`). Fill every `###` heading.

```markdown
## Sprint SPR-01 — Handoff

### Status
`done` | `in_progress` | `blocked` — (one line)

### Files touched
- `docs/agent-execution/HARD_TO_VARY.md` — (one line what changed)
- `docs/agent-execution/TEMPLATES.md` — (one line)

### Milestones (checkboxes)
- [ ] M1: Write HARD_TO_VARY.md — Phase A–E + forbidden F1–F8
- [ ] M2: Add TEMPLATES.md — Env Card, Failure Dossier, Scope Map, Handoff Packet

### Verification gate results

| Gate | Command | Exit | Outcome |
|------|---------|------|---------|
| Doc lint | `test -f docs/agent-execution/HARD_TO_VARY.md` | 0 | file exists |

(Paste Env Card above this table for code sprints.)

### Decisions mid-flight
- (decision — reverse-if)

### Assumptions surfaced
- (assumption — how verified or risk accepted)

### Steelman rejected alternative
**Fast path:** (e.g. “fix looks right, ship without matrix”)
**Why it loses:** (regression gate, scope map, operator trust — be specific)

### Open questions
- (question → owner / follow-up sprint)

### Next sprint can start when
- (e.g. SPR-02 repro script exists; this handoff merged)

### Out-of-scope temptations
- (temptation — did not act / noted only)
```

---

## Minimal session paste (all four)

For a short chat close, paste in order: **Env Card → Failure Dossier (if debugging) → Scope Map (if multi-path) → Handoff Packet**.

```markdown
<!-- 1. Env Card -->
## Env Card
| Field | Value |
|-------|-------|
| Date (UTC) | |
| Repo root (`pwd`) | |
| Branch | |
| Commit SHA | |
| Python | |
| Python version | |
| LLM contacted this session | |
| Network required for gates | |

<!-- 2. Failure Dossier (Phase A investigations only) -->
## Failure Dossier
**LLM contacted on failure path:**
### Numbered failure chain
1. …

<!-- 3. Scope Map (Phase B — required before platform claims) -->
## Scope Map
| ID | Path | Test status | Evidence | Live LLM |
|----|------|-------------|----------|----------|

<!-- 4. Handoff Packet (every sprint) -->
## Sprint SPR-XX — Handoff
### Status
### Files touched
### Milestones (checkboxes)
### Verification gate results
### Decisions mid-flight
### Assumptions surfaced
### Steelman rejected alternative
### Open questions
### Next sprint can start when
### Out-of-scope temptations
```