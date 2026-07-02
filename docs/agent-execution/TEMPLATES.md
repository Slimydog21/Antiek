# Agent execution templates

Copy-paste blocks for ANT-H2V and any Antiek agent session. **Do not delete headings** in the Handoff Packet — use `N/A — reason` when a section does not apply.

Protocol: `docs/agent-execution/HARD_TO_VARY.md`

---

## Env Card

Paste at the top of every handoff and before canonical verify (Phase D).

```markdown
### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | YYYY-MM-DD |
| Repo root (`pwd`) | `/absolute/path/to/Antiek` |
| Branch | `caffen/ant-exec-spr01` |
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

1. **Trigger:** `POST /research/plans` without `sub_questions[]` — `interfaces/research/api/cascade_routes.py:line`
2. **Branch:** `_decompose()` — `file:line`
3. **Adapter:** `DispatchDecomposer.decompose` — `roles/cascade_planner/planner.py:57-69`
4. **Exception:** `TypeError` — (paste message)
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
**Log path:** `reports/repro-cascade.log` or paste inline

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

### Entry points

| ID | Path / trigger | Production hook | Test status | Evidence | Live LLM |
|----|----------------|-----------------|-------------|----------|----------|
| E1 | POST `/research/plans` omit `sub_questions` | `DispatchDecomposer` | `untested` | — | `required` for operator card |
| E2 | POST `/research/plans` with `sub_questions` | fixed decomposer | `tested` | `tests/test_cascade_create_plan_light.py:line` | `no` |
| E3 | Loop1 investigations bus | `make_decomposer_handler` | `untested` | `file:line` | `yes` |
| E4 | Mountain shell visibility | `apps/reading/src/scene/Scene.tsx` | `tested` | `docs/ams-v2/mountain-shell-v2-verification.md` | `no` |

**Test status legend:** `tested` | `untested` | `live-LLM-required`

### Explicitly out of scope (this session)

- (bullet)

### Temptations resisted

- (what you did NOT do and why)
```

---

## Handoff Packet

Superset of `docs/specs/ant-h2v/sprint-01-agent-protocol.html` handoff footer (adds `### Env Card`, `### Not proved`, `### Gate results` with log path). Fill every `###` heading below. **`### Not proved` before `### Status`.**

```markdown
## Sprint SPR-01 — Handoff

### Env Card
(paste Env Card table here)

### Not proved
- Live LLM on all decompose paths (operator card not run)
- Bus parity with HTTP auto-decompose
- (bullet — each must name why it is out of scope or deferred)

### Status
`done` | `in_progress` | `blocked` — (one line)

### Files touched
- `docs/agent-execution/HARD_TO_VARY.md` — Phase A–E, F1–F8, lineage table
- `docs/agent-execution/TEMPLATES.md` — Env Card, dossier, scope map, handoff

### Milestones (checkboxes)
- [x] M1: Write HARD_TO_VARY.md — Phase A–E + forbidden F1–F8
- [x] M2: Add TEMPLATES.md — ≥8 `###` headings + Gate results log path

### Gate results

| gate | command | exit | log path |
|------|---------|------|----------|
| Doc exists | `test -f docs/agent-execution/HARD_TO_VARY.md && test -f docs/agent-execution/TEMPLATES.md` | 0 | (inline) |
| Heading count | `rg -c '^### ' docs/agent-execution/TEMPLATES.md` | 0 | (stdout) |

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
- (e.g. SPR-02 theater taxonomy merged; handoff linter green)

### Out-of-scope temptations
- (temptation — did not act / noted only)
```

---

## Minimal session paste (all four)

For a short chat close, paste in order: **Env Card → Failure Dossier (if debugging) → Scope Map (if multi-path) → Handoff Packet**.

```markdown
### Env Card
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

## Failure Dossier
**LLM contacted on failure path:**
### Numbered failure chain
1. …

## Scope Map
### Entry points
| ID | Path | Test status | Evidence | Live LLM |
|----|------|-------------|----------|----------|

## Sprint SPR-XX — Handoff
### Env Card
### Not proved
### Status
### Files touched
### Milestones (checkboxes)
### Gate results
### Decisions mid-flight
### Assumptions surfaced
### Steelman rejected alternative
### Open questions
### Next sprint can start when
### Out-of-scope temptations
```

---

## Heading index (≥8 required `###`)

| # | Heading | Phase |
|---|---------|-------|
| 1 | `### Env Card` | D |
| 2 | `### Not proved` | E |
| 3 | `### Status` | E |
| 4 | `### Files touched` | E |
| 5 | `### Milestones (checkboxes)` | E |
| 6 | `### Gate results` | D |
| 7 | `### Steelman rejected alternative` | E |
| 8 | `### Open questions` | E |

Failure Dossier and Scope Map add additional `###` blocks for investigations; the handoff packet alone satisfies the sprint minimum.

---

## Research artifact handoff (ANT-AHT)

After DRW or long agent session, attach exported HTML path:

```markdown
### Research artifact
- Export: `python -m substrate.research_artifact <investigation_id>`
- Path: `~/.antiek/research-artifacts/<investigation_id>.html`
- Transport doc: `docs/agent-execution/RESEARCH_ARTIFACT_TRANSPORT.md`
```