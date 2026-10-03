# Cockpit two-pane layout — design brief for Kimi (2026-09-24)

**Audience:** Kimi (Antiek workspace `w7`, tab `kimi` / pane `w7:pT`), picking up UI/design after Opus Nudge/Sweep hit weekly limits.
**Author:** executor agent on behalf of Faisal (operator).
**Status:** C1–C5 **RATIFIED BY FAISAL 2026-09-24 (18:20 AST)**. Build to §4. Still build ON TOP of Opus Nudge/Sweep work — do not rewrite it. Copy §4 into `specs/antiek-mothership/DECISIONS.md` as a new entry so the Opus spec agrees.
**Related Opus records (read these first):**
- `specs/antiek-mothership/DECISIONS.md` (D1–D6; add ratified C1–C5 as a new entry)
- `specs/antiek-mothership/DESIGN-MODEL.md`
- `platform/.../docs/decisions/mothership-keys-herdr-prefix.md` (D2 keymap) — worktree `mothership-01`
- Branch `design/mothership-01-shell-keymap` (MS-01)
- Branch `design/mothership-04a-tab-tree-model-20260924` / worktree `ms04-tab-tree` (MS-04 `tabTree.ts`)
- Design waves W1–W7 worktrees (`w1-tokens-foundation` … `w6-visual-gates`, `w7-crashes`)

---

## 0. Standing order

**Build ON TOP of the Opus Nudge/Sweep mothership + design-wave work. Do not rewrite it.**

Extend named files and components. Do not introduce a parallel keymap, parallel token set, or a second shell chrome. C1–C5 below are now operator law and reinterpret D1/D5 as modes. Still do not invent a parallel keymap, token set, or tab-tree model — extend the Opus files named in §2.

---

## 1. Faisal's new direction (operator intent, 2026-09-24 evening)

Paraphrased from Faisal; this is the product feel he wants next:

1. **One core asset — the mothership / cockpit.** One platform for research, reading, and writing. All the controls. Feels like operating a plane/spaceship cockpit — not three separate product shells you "mode-switch" between as primary navigation.
2. **Herdr as the workflow metaphor.** A knowledge worker moves through work with keys the way a programmer drives Herdr. Keyboard-first is non-negotiable.
3. **Two keybinding levels.**
   - **Project level:** switch between projects (workstations).
   - **Document level:** tabs for everything spawned from one document — links, footnotes, related documents, deep researches triggered from that document.
4. **Omarchy visual model (Hyprland tiling).** Two tall rectangles side by side that **do not cover the whole screen**, so the **background and a left toolbar stay visible**. Omarchy-style pane focus: e.g. Cmd+Left/Right between panes, Cmd+F to fullscreen a pane. Exact bindings are your call but must *feel* like Omarchy/Herdr (and must not break the D2 keymap table — extend it). **Note:** C3 (ratified) forbids Cmd+Left/Right and Cmd+F; use prefix/chord instead.
5. **LEFT pane = always the core/primary material.** Downloaded webpage, book, research report. Tabbed (document-level tabs, key-toggleable). Above that, a **project-level tab layer** so the left pane's whole document set switches with one key.
6. **RIGHT pane = AI subagents, also tabbed** (for research/reading). Documents live under the left pane, not under agents — one subagent can work across several documents. An agent that says "this other document is interesting" opens that document as a **new tab in the left pane's document space**. **Note:** C4 (ratified) — the right pane IS the companion (D3); agents are tabs inside it.
7. **Reading workflow = same shape as research:** document left, agents right.
8. **Writing workflow is different:** writing on the LEFT; **outline on the RIGHT**. Building-blocks outline: right pane has **one tab per block**; inside each block tab, drag-and-drop / structure which documents inform that block. Left pane shows plain-text output: first tab = full body, then one tab per section — key through sections and edit sentences at a forensic grain. **Note:** C5 (ratified) — agents via AI sidecar (`mod+/`), not occupying the Write right pane.

---

## 2. What Opus already established (extend these)

### 2.1 Spec / decisions (Nudge lane A + Sweep lane B)

| ID | Decision | Where |
|---|---|---|
| D2 | herdr-style **prefix** (default `ctrl+b`) + **ctrl+alt** direct chords; one keymap table; key sheet from the same table | `DECISIONS.md`, `mothership-keys-herdr-prefix.md`, `keymap.ts` |
| D3 | Companion = project Companion tab + per-evidence companion **rail** | `DECISIONS.md`, DESIGN-MODEL §6 — **elevated by C4 to the right pane** |
| D4 | Diligence opt-in per flag + daily cap + attention inbox | `DECISIONS.md` |
| D5 | Reading as first-class mothership (Kindle + project reading doors) | `DECISIONS.md` — **reinterpreted by C1 as a mode** |
| D6 | Tabs = **infinitely nested branch tree** (footnotes/refs/islands spawn child tabs; hierarchical numbers `3.2.1`) | `DECISIONS.md`, DESIGN-MODEL §2a |
| D1 | Originally two motherships (Research/Writing); amended by D5 to **three** shells over shared projects | `DECISIONS.md` — **reinterpreted by C1 as modes inside one cockpit** |

Lane split: Nudge = UX shells/tabs/keys/islands (`design/mothership-*`); Sweep = thread/data contract (`feat/mothership-*`, `THREAD-CONTRACT.md`). Critic: Codex. Train merge via Nudge's train when Opus returns.

### 2.2 Concrete code to extend (do not fork)

**Keymap / shell (MS-01 — branch `design/mothership-01-shell-keymap`, worktree `mothership-01`):**
- `apps/reading/src/components/hotkeys/keymap.ts` — THE table (`KEYMAP`, `ACTIONS`, prefix + chords)
- `apps/reading/src/workspace/shortcuts.ts` — the one dispatcher (`useWorkspaceShortcuts`)
- `apps/reading/src/components/hotkeys/prefixState.ts`, `bindings.ts`, key sheet views
- Landed semantics: prefix never arms in text fields; `ctrl+alt` matched on `e.code`; Mac vs other for `mod+b`; carrier fix head `8e007f2cb`

**Shipped / reserved D2 bindings (selected):**
- Prefix: `ctrl+b` then `g` (switcher), `?` (key sheet), `b` (sidebar/project tree); reserved for later: tabs 1–9, n/p, c, w, m, u, o, t, f, r, a, i, shift+x, shift+n (MS-03/MS-04)
- Direct: `ctrl+alt+b` sidebar; legacy SPR-08 `mod+k` palette, `mod+[` / `mod+]` panel focus, `mod+/` AI sidecar, product doors `mod+j/e/y/u/o/i`, etc.

**Tab tree (MS-04 M1 — worktree `ms04-tab-tree`, commit `5888cf9ca`):**
- `apps/reading/src/workspace/tabTree.ts` (+ `.test.ts`, `.property.test.ts`)
- Pure branch model: parent/child, prune vs close-only, multi-device prune rules, hierarchical numbering — **this is the document-level tab substrate** Faisal is describing. Wire UI to it; do not invent a second tab model.

**Layout / chrome already on the design chain:**
- `apps/reading/src/workspace/PanelLayout.tsx` — left dock / main / right dock / bottom dock — **extend with Omarchy inset preset (C2)**
- `apps/reading/src/shell/NavRail.tsx` — left product rail (the "left toolbar that stays visible")
- `apps/reading/src/shell/SceneChrome.tsx`, `ProjectTree.tsx`, `Trail.tsx` / `TrailJump.tsx` (renamed from ThreadBreadcrumb/ThreadJump)
- `apps/reading/src/shell/MascotStation.tsx` — docked mascot
- AI sidecar toggle (`aisidecar.toggle`, `mod+/`) — one-keystroke agents in Write mode (C5); research/reading agents live as tabs in the right companion pane (C4)

**Design tokens / craft (W1–W7 waves):**
- `apps/reading/src/design/tokens.ts` + `tokens.css` — "paper, ink, and one sun" (`sun #F5DF24`, danger `#B82E1C`, day/night semantic layer)
- `DESIGN_LANGUAGE.md`, `FEEL_CONTRACT.md`, shared `LoadingState` / `EmptyState` / `ErrorState`, prose layer, motion (`design/motion*`)
- Keep token discipline; no new palette for the cockpit.

**Routes / product doors (SPR-08 legacy, still in keymap):**
- Research `/`, Read `/library` + `/read/:documentId`, Write `/write`, Speak `/speak`, Home `/home`

**Specs program Kimi already owns (vision map):**
- Units 1–4, 7 frontend; units 5–6 were partner — open spec PRs include `#3425` anchor-first, `#3428` island, `#3431` workstation-tabs, `#3433` reading-global, `#3435` autonomous-diligence. Continue those; **do not drop them** for this brief — the cockpit brief is the *chrome* that hosts that work.

---

## 3. How to reconcile (preferred synthesis — build path)

Treat Faisal's cockpit as the **chrome metaphor** and Opus's mothership decisions as the **object model**, with C1–C5 (ratified) resolving the former conflicts.

| Faisal ask | Opus substrate to extend | Build guidance |
|---|---|---|
| Keyboard-first / Herdr | D2 keymap + dispatcher | Pane focus + fullscreen as **new rows** in `keymap.ts` on prefix/`ctrl+alt` (C3). Never Cmd+Left/Right or Cmd+F. Never a second listener. |
| Project-level switching | workstation = project (DESIGN-MODEL); `prefix+w` reserved | Implement project tab strip / hop on reserved keys; one key switches the left pane's document set. |
| Document-level tabs (links, footnotes, deep research) | D6 + `tabTree.ts` | UI: left-pane tab strip + Trail breadcrumb + tree panel (`prefix+t` / `ctrl+alt+y`). Spawns = child tabs. |
| Left = primary material | main slot / reader surfaces | Left rectangle hosts reader / report / write body. Keep Kindle-grade reading from D5 §2b. |
| Right = agents (research/reading) | companion (D3) + thread list | **C4:** right pane IS companion; each agent is a tab. Agent "open that doc" → `tabTree` spawn into **left** document space. |
| Writing: outline right / body left | Writing surfaces + outline block tabs | **C5:** right = one tab per building-block + DnD sources; left = full body + per-section tabs; agents via `mod+/` sidecar. |
| Omarchy insets + left toolbar visible | `PanelLayout` + `NavRail` | **C2:** Omarchy inset two-pane is a layout **preset inside** `PanelLayout` — extend, do not replace. |
| One cockpit feel | D1/D5 product doors | **C1:** one chrome; Research/Read/Write (and Speak/Home) are modes via `mod+j/e/y/u/o` / `prefix+m`. Keep D1/D5 content; no separate shells. |

---

## 4. Conflicts C1–C5 — RATIFIED BY FAISAL 2026-09-24 (18:20 AST)

These were open questions; the operator ratified all five. **Build to these.** Also copy them into `specs/antiek-mothership/DECISIONS.md` as a new decision entry (e.g. D7) so the Opus mothership spec and this brief agree.

### C1 — One cockpit shell (reinterprets D1/D5) — RATIFIED
**One cockpit shell.** Opus's Research, Read and Write doors (`mod+j` / `mod+e` / `mod+y`, plus Speak and Home) become **modes inside it**, not separate motherships. D1/D5 content is kept; their framing is reinterpreted as modes within the single chrome. `prefix+m` (and product doors) switch mode, not shell.

### C2 — Omarchy insets as a PanelLayout preset — RATIFIED
The Omarchy inset two-pane view (gaps, background and left toolbar visible) is a **layout preset inside** Opus's `PanelLayout`. **Extend** `PanelLayout.tsx`; do **not** replace or rebuild it.

### C3 — Keys stay D2; Omarchy-feel aliases only where free — RATIFIED
Opus's Herdr-style prefix keys (`ctrl+b` then a key, per D2, plus the `ctrl+alt` chords and the SPR-08 `mod+[` / `mod+]`) stay the **real** key system. Add Omarchy-feel aliases **only** where the browser does not already use the key. **Do NOT** bind Cmd+Left/Right (cursor move in text fields) or Cmd+F (browser find). Fullscreen-pane toggle and pane-focus move go on **prefix / chord** keys instead (new rows in `keymap.ts`, with prefix twins).

### C4 — Right pane IS the companion; agents are tabs — RATIFIED
The right pane **IS** Opus's companion (D3). Each AI agent is a **tab inside it**. Agents can open documents as new tabs in the left pane's document space, using `tabTree.ts` (MS-04 / D6).

### C5 — Write mode: outline on the right; agents via sidecar — RATIFIED
In **Write** mode the right pane shows **one tab per outline block**, with drag-and-drop of source documents into each block. The left pane shows the full-body document, then one tab per section. Agents stay one keystroke away through Opus's AI sidecar (`mod+/` / `aisidecar.toggle`).

---

## 5. Immediate execution checklist for Kimi

1. Read this file + `specs/antiek-mothership/DESIGN-MODEL.md` + `mothership-keys-herdr-prefix.md`.
2. Inventory branches/worktrees: `mothership-01`, `ms04-tab-tree`, `w1-tokens-foundation`…`w7-crashes`. Prefer continuing those heads over starting greenfield.
3. Finish current open spec units / merge loops first; then prototype **cockpit chrome** that:
   - keeps `keymap.ts` / `shortcuts.ts` as sole key owners;
   - mounts document tabs on `tabTree.ts`;
   - uses existing tokens + NavRail;
   - implements C2 Omarchy inset preset inside `PanelLayout`;
   - implements C4 companion-as-right-pane with agent tabs (Research/Reading modes);
   - implements C5 Writing outline tabs; agents via `mod+/`;
   - does not block units 1–4/7 specs.
4. Cite C1–C5 (RATIFIED) at the top of any PR / handoff; **copy them into `specs/antiek-mothership/DECISIONS.md` as a new decision entry** so the Opus spec and this brief agree.
5. Continue merge-watch on your open spec PRs (`#3425`, `#3428`, `#3431`, `#3433`, `#3435`, `#3437`) in parallel — cockpit chrome must not abandon that train.

---

## 6. Explicit non-goals for this brief

- Do not push to `main` or deploy.
- Do not interrupt or rewrite Nudge/Sweep sessions (they are usage-capped until Sep 26 ~15:00 Asia/Riyadh).
- Do not invent a second keymap, token file, or tab-tree model.
- Do not silently drop D2/D6.
- Do not bind Cmd+Left/Right or Cmd+F (C3).

---

*End of brief. Path on Mini: `~/Antiek/docs/decisions/cockpit-two-pane-layout-2026-09-24.md`*
