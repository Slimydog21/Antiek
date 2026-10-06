#!/usr/bin/env python3
"""Render the lane-A sprint pages from structured data (htmlspec sprint template markup).

Each sprint is authored by hand below; this file only guarantees identical markup and the
standalone-briefing preamble on every page. Run: python3 sprints.py && python3 build.py
"""
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = "2026-09-24"
PROJECT = "The Antiek motherships"

BRIEFING = (
    "<p>Antiek is the operator's research + reading + writing workstation. The repository is "
    "<code>Slimydog21/Antiek</code>. Its main checkout at <code>/Users/slimydog/Antiek/platform</code> sits on a "
    "<strong>stale branch</strong>, so never build or test there. Create your own worktree instead: "
    "<code>git -C /Users/slimydog/Antiek/platform fetch -q origin &amp;&amp; git -C /Users/slimydog/Antiek/platform "
    "worktree add -b &lt;branch&gt; /Users/slimydog/Antiek/platform/.claude/worktrees/&lt;name&gt; &lt;base&gt;</code>, "
    "then work only there, by absolute path.</p>"
    "<p>The frontend is <code>apps/reading</code>: React 18, react-router 6, Vite, Tailwind with the W1 "
    "semantic tokens, Lemon UI primitives in <code>src/components/lemon</code>, and Zustand stores (for example "
    "<code>src/workspace/WorkspaceStore.ts</code>). Run these from <code>apps/reading</code> "
    "(<code>npm --prefix &lt;wt&gt;/apps/reading …</code>):</p>"
    "<ul>"
    "<li><code>npm ci</code>: a real install, never a symlinked <code>node_modules</code> (Vite's fs.allow breaks pdf.js).</li>"
    "<li><code>npm run typecheck</code>: tsc -b --noEmit.</li>"
    "<li><code>npm run test -- --no-color</code>: vitest. It must run with cwd = <code>apps/reading</code>, because some tests read module text by relative path.</li>"
    "<li><code>npm run build:check</code>: the entry <code>index</code> chunk must stay under 700 KB gz. Lazy-load new surfaces, as W7 did for the operator pages.</li>"
    "<li><code>npm run check:tokens</code>.</li>"
    "</ul>"
    "<p>Stories are <code>*.stories.tsx</code>. jest-dom matchers are <em>not</em> installed, so use "
    "<code>toBeTruthy()</code>, <code>toBeNull()</code> and <code>.textContent</code>. The backend is FastAPI + DuckDB behind a single writer; "
    "lane A edits no backend file unless a milestone says so.</p>"
    "<p><strong>Never edit lane B's in-flight files:</strong> "
    "<code>substrate/research_artifact/{context,build_body}.py</code>, <code>substrate/event_log/events.py</code>, "
    "<code>substrate/provenance/pointers.py</code>, <code>roles/note_taker/{living_note,distill_query}.py</code>. "
    "If the UI needs a field, it goes in <code>THREAD-CONTRACT.md</code>.</p>"
    "<p><strong>Merging:</strong> push your branch (branch pushes run no CI here), write "
    "<code>&lt;wt&gt;/.lane/PR_TITLE.txt</code> and <code>PR_BODY.md</code>, and message the session \"Antiek Nudge\", which "
    "is the only merger. Never open or merge a PR yourself.</p>"
    "<p><strong>Critic:</strong> <code>codex exec -s workspace-write --skip-git-repo-check \"&lt;brief&gt;\" &lt; /dev/null</code> "
    "(gpt-6-sol). Without <code>&lt; /dev/null</code> it waits on stdin forever. In a background Claude session, never call "
    "EnterWorktree while a workflow is running, because it pins every agent to one worktree.</p>"
    "<p><strong>Binding operator rulings:</strong> <code>/Users/slimydog/Antiek/specs/antiek-mothership/DECISIONS.md</code> (D1–D6). "
    "The model is in <code>DESIGN-MODEL.md</code>, the evidence in <code>GAPS.md</code>, <code>ground/</code> and <code>verify/</code>, all in the same folder.</p>"
)

def e(s):
    return s  # content below is authored as trusted HTML fragments

def render(sp):
    ms = []
    for i, m in enumerate(sp["milestones"], 1):
        crit = "".join(f"<li>{c}</li>" for c in m["criteria"])
        files = "".join(f'<span class="file">{html.escape(f)}</span>' for f in m["files"])
        ms.append(f'''
    <div class="milestone">
      <div class="num">{i}</div>
      <div>
        <div class="title">{m["title"]}</div>
        <p class="desc">{m["desc"]}</p>
        <div class="criteria"><strong>Acceptance criteria</strong><ul>{crit}</ul></div>
        <div class="files">{files}</div>
      </div>
    </div>''')
    rig = sp["rigor"]
    cards = "".join(f'''
      <div class="rigor-card"><span class="label">{lab}</span><h4>{h}</h4><p>{rig[k]}</p></div>'''
        for k, lab, h in [("honesty", "1 · Intellectual honesty", "Calibrate confidence to evidence"),
                          ("fairness", "2 · Fairness", "Steelman the rejected alternative"),
                          ("rigor", "3 · Rigor", "Claims are mechanically checkable"),
                          ("diligence", "4 · Diligence", "Read before writing"),
                          ("defensibility", "5 · Defensibility", "Decisions survive turnover")])
    up = "".join(f'<li>{a} — <span class="muted">{b}</span></li>' for a, b in sp["upstream"])
    ext = "".join(f"<li>{x}</li>" for x in sp["external"])
    oos = "".join(f"<li>{x}</li>" for x in sp["out_of_scope"])
    gates = "".join(f"<tr><td><strong>{g}</strong></td><td><code>{html.escape(c)}</code></td><td>{x}</td></tr>" for g, c, x in sp["gates"])
    mlist = "\n".join(f"- [ ] M{i}: {html.escape(m['title'])} — &lt;result&gt;" for i, m in enumerate(sp["milestones"], 1))
    glist = "\n".join(f"- {html.escape(g)}: pass | fail | skipped (why)" for g, _, _ in sp["gates"])
    h = sp["harness"]
    lenses = "".join(f"<li>{lens}</li>" for lens in h["lenses"])
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{sp["id"]} · {html.escape(sp["title"])} — {PROJECT}</title>
<style>
/*STYLE*/
</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <p class="eyebrow"><a href="index.html">&larr; {PROJECT}</a> · Sprint {sp["id"]}</p>
    <h1>{sp["title"]}</h1>
    <p class="tagline">{sp["tagline"]}</p>
    <div class="meta-row">
      <span class="tag tag--blue"><span class="dot"></span>Wave {sp["wave"]}</span>
      <span class="tag tag--yellow"><span class="dot"></span>{sp["status"]}</span>
      <span class="tag tag--grey">Budget: {sp["budget"]}</span>
      <span class="tag tag--grey">Owner: {sp["owner"]}</span>
    </div>
  </header>

  <section class="block">
    <h2>Parent context</h2>
    <p class="lede">Read this before starting. It is everything you need to execute this sprint without opening the master spec.</p>
    {BRIEFING}
    {sp["context"]}
    {('<div class="callout callout--warn"><strong>Contract facts (THREAD-CONTRACT.md rev 7, signed by both lanes 2026-09-26): these override any older wording on this page.</strong><ul>' + "".join(f"<li>{c}</li>" for c in sp["contract"]) + '</ul></div>') if sp.get("contract") else ""}
    <div class="callout callout--info"><strong>Where this sprint sits:</strong> {sp["position"]}</div>
  </section>

  <section class="block">
    <h2>Goal</h2>
    <p><strong>{sp["goal_line"]}</strong></p>
    {sp["goal"]}
  </section>

  <section class="block">
    <h2>Technical milestones</h2>
    <p class="lede">Numbered. Each milestone has explicit acceptance criteria and the files it touches. Do not declare a milestone complete unless the criteria are mechanically verified.</p>
    {"".join(ms)}
  </section>

  <section class="block">
    <h2>Rigor — operating manual for this sprint</h2>
    <p class="lede">How to execute well. Each value has been adapted to this sprint's specific work.</p>
    <div class="rigor">{cards}
    </div>
  </section>

  <section class="block">
    <h2>Dependencies</h2>
    <p class="lede">What must be true before this sprint can start. Verify each one before executing milestone 1.</p>
    <div class="two-col">
      <div><h3>Upstream sprints</h3><ul>{up}</ul></div>
      <div><h3>External systems &amp; configs</h3><ul>{ext}</ul></div>
    </div>
  </section>

  <section class="block">
    <h2>Out of scope</h2>
    <p class="lede">Explicit non-goals. These are the most-tempting expansions; do not pursue them here.</p>
    <ul>{oos}</ul>
    <div class="callout callout--warn"><strong>If you find yourself wanting to do one of the above:</strong> stop, write a note in the handoff packet, and proceed with the original scope.</div>
  </section>

  <section class="block">
    <h2>Verification gates</h2>
    <p class="lede">Before declaring this sprint complete, run each of these and record the result in the handoff packet.</p>
    <table class="spec">
      <thead><tr><th style="width: 24%">Gate</th><th style="width: 48%">How to verify</th><th style="width: 28%">Expected result</th></tr></thead>
      <tbody>{gates}</tbody>
    </table>
  </section>

  <section class="block">
    <h2>Handoff packet</h2>
    <p class="lede">What this sprint hands back when done. Paste this block, filled in, at the end of your final message. The same content goes into <code>.lane/PR_BODY.md</code>.</p>
    <pre><code>## Sprint {sp["id"]} — Handoff
### Status
DONE | BLOCKED | PARTIAL (and why)
### Branch / head / base
design/mothership-… @ &lt;sha&gt; on &lt;base sha&gt;
### Files touched
- path:line — what changed and why
### Milestones
{mlist}
### Verification gate results
{glist}
### Decisions made mid-flight
- Decision: what / why / what would reverse it
### Assumptions surfaced (rigor #1)
- …
### Steelman of rejected alternative (rigor #2)
- …
### Open questions discovered
- Question — who can answer
### Next sprint can start when
- {sp["next_when"]}
### Out-of-scope temptations encountered
- What I wanted to do, what I did instead
</code></pre>
  </section>

  <section class="block" id="harness-hint"
           data-harness-pattern="{h["pattern"]}"
           data-harness-fanout-unit="{html.escape(h["unit"])}"
           data-harness-verifier-lenses="{html.escape(" | ".join(h["lenses_short"]))}"
           data-harness-rounds-floor="{h.get("floor", 1)}"
           data-harness-rounds-cap="{h.get("cap", 6)}">
    <h2>Execution harness hint <span class="tag tag--grey">optional · for /caffenagent</span></h2>
    <p class="lede">For the executor, not a human. If this block is absent or says <code>inline</code>, run the sprint inline with no fan-out.</p>
    <div class="two-col">
      <div><h3>Recommended pattern</h3><p><code>{h["pattern"]}</code></p><p class="muted">{h["why"]}</p></div>
      <div><h3>Fan-out unit</h3><p>{h["unit"]}</p></div>
    </div>
    <h3>Recommended verifier lenses</h3>
    <ul>{lenses}</ul>
    <div class="callout callout--info"><strong>Irreversible acts stay in the main loop.</strong> Sub-agents investigate, build in worktrees and verify. Pushing is done by the sprint owner, and merging is done only by Antiek Nudge's train.</div>
  </section>

  <footer class="spec-footer">
    Sprint {sp["id"]} of {PROJECT} · <a href="index.html">Back to master spec</a> · Generated {GEN}
  </footer>
</main>
</body>
</html>
'''

SPRINTS = []

# ---------------------------------------------------------------- MS-01
SPRINTS.append(dict(
    id="MS-01", slug="shell-stabilisation-keymap", wave=0, status="ready", budget="7 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Shell stabilisation + one keymap",
    tagline="Fix the five shell defects that would poison every mothership build. Give the app one keymap: herdr's prefix plus ctrl+alt chords, one table, one dispatcher and one key sheet.",
    context=(
        "<p><strong>What this sprint is about.</strong> Grounding on main <code>15e78e276</code> proved four shell defects by running "
        "the real modules in jsdom (<code>ground/lane-a-shell-workstations.json</code>). A refuter added a fifth.</p>"
        "<ul>"
        "<li><strong>F1:</strong> ⌘K cancels itself, because <code>CommandPalette</code>'s own keydown handler and AppShell's <code>PALETTE_TOGGLE</code> both toggle.</li>"
        "<li><strong>F2:</strong> on fresh storage, AppShell's hydration effect runs after the route's <code>PanelHost</code> starters open (child effects run first) and wipes them.</li>"
        "<li><strong>F3:</strong> AppShell calls <code>useParams</code> outside the inner <code>&lt;Routes&gt;</code>, so the per-investigation layout key is never used.</li>"
        "<li><strong>F4:</strong> a nested <code>PanelLayout</code> (<code>AppShell.tsx:151</code> + <code>PanelHost.tsx:79</code>) renders every docked panel twice.</li>"
        "<li><strong>F5:</strong> <code>ResearchWorkstation</code> never remounts across <code>/inv/:id</code>, so starters open only once.</li>"
        "</ul>"
        "<p><strong>F9:</strong> the app has no single keymap owner. At least three window-level handlers claim ⌘ combos, and every plain ⌘+letter is already bound. "
        "The operator ruled (D2) for a herdr-style prefix (<code>ctrl+b</code>) plus <code>ctrl+alt</code> direct chords. That "
        "supersedes the ratified SPR-08 no-leader rule. herdr's own keyboard doc is saved at <code>research/herdr-keyboard-v0.9.1.mdx</code>, and the key table is in "
        "<code>DESIGN-MODEL.md</code> §2 and §2a.</p>"
        "<p><strong>Base.</strong> The unmerged design chain rewrites the same shell files: W1 tokens → W3 "
        "shell/states/prose, <code>origin/design/w3-shell-states-prose-20260923</code> (it contains W1 <code>7144b8e6b</code>), and W7 crashes, "
        "<code>origin/design/w7-crashes-20260924</code>, which already hoisted <code>PanelLayout</code>'s hooks. Base on the W3 head and "
        "merge W7 into it. If <code>origin/main</code> already contains all three, base on <code>origin/main</code> instead. Branch: "
        "<code>design/mothership-01-shell-keymap</code>.</p>"),
    position="Wave 0, the first lane-A sprint. MS-03, MS-04 and MS-05 build on its keymap and its stable shell. It needs nothing from lane B.",
    goal_line="Every shell defect found in grounding is re-proven, fixed and pinned by a test that fails on the base. Every key in the app is dispatched from ONE table that renders its own key sheet.",
    goal=("<p>After this sprint, the operator presses <code>ctrl+b</code> and sees a quiet <em>prefix armed</em> chip. The next key does what "
          "herdr's would, and <code>prefix+?</code> shows every binding with a <code>/</code> filter. ⌘K opens the palette from anywhere. "
          "A fresh investigation docks its sidebar and chat, once each. Nothing about the product's surfaces changes yet. This sprint "
          "gives MS-03 and MS-04 a shell and a keymap they can trust.</p>"),
    milestones=[
        dict(title="Worktree on the design chain; baseline recorded",
             desc="Create the worktree from the W3 head with W7 merged, or from main if the chain has landed. Record the baseline before changing anything: tsc error count, the vitest files/tests line, <code>build:check</code> entry size and headroom, and the SHAs used.",
             criteria=["The handoff quotes the baseline tsc, vitest and build:check lines, with the base SHAs.",
                       "Any merge conflict between W3 and W7 is resolved and listed file by file."],
             files=["(worktree setup only)"]),
        dict(title="Re-prove F1–F5 on the base, each as a failing test",
             desc="For each defect, write a vitest + @testing-library test that fails on the base. F1: ⌘K with focus on <code>document.body</code> opens the palette. F2: fresh localStorage + <code>/inv/abc</code> gives the investigation sidebar and chat docked. F3: the per-investigation layout key <code>antiek.workspace.inv.&lt;id&gt;</code> is written and \"Reset layout (this investigation)\" clears it. F4: exactly one left dock in the DOM. F5: navigating <code>/inv/a</code> → <code>/inv/b</code> opens b's chat starter.",
             criteria=["Each test fails on the base. Quote the failure. If W3 or W7 already fixed one, record it as \"fixed upstream by &lt;sha&gt;\" and keep the test as a guard.",
                       "The tests live next to the code they cover (AppShell, PanelHost, ResearchWorkstation)."],
             files=["apps/reading/src/AppShell.*.test.tsx", "apps/reading/src/workspace/PanelHost.*.test.tsx", "apps/reading/src/modes/ResearchWorkstation/*.test.tsx"]),
        dict(title="Fix F1–F5 at their root",
             desc="F1: one palette toggle owner, the shell's. Remove the in-component handler, or ignore events already handled (<code>e.defaultPrevented</code>). F2: hydrate before starters open, or merge starters into the hydrated layout. F3: derive the investigation id with <code>useMatch</code>/<code>matchPath</code> on the location, not <code>useParams</code> outside the routes. F4: a single <code>PanelLayout</code> owner. F5: key the workstation by investigation id, or reopen starters on id change.",
             criteria=["All tests from milestone 2 pass.",
                       "No other test regresses; the full suite count is at least baseline plus the new tests."],
             files=["apps/reading/src/AppShell.tsx", "apps/reading/src/components/CommandPalette.tsx", "apps/reading/src/workspace/PanelHost.tsx", "apps/reading/src/workspace/useWorkspaceHydration.ts", "apps/reading/src/modes/ResearchWorkstation/index.tsx"]),
        dict(title="ONE keymap table + dispatcher (the prefix engine)",
             desc="Create <code>src/components/hotkeys/keymap.ts</code>. It is a single typed table of <code>{action, prefixKey?, chord?, scope, origin}</code>, where origin is <code>herdr-default</code>, <code>D2</code> or <code>legacy-SPR-08</code>. One window-level dispatcher owns every global key.<ul>"
                  "<li><strong>Prefix:</strong> default <code>ctrl+b</code>, configurable. It stays armed until the next key or Esc, with no timeout, as in herdr/tmux. A visible \"prefix armed\" chip shows while it is armed.</li>"
                  "<li><strong>Chords:</strong> the <code>ctrl+alt</code> family, matched on <code>KeyboardEvent.code</code> so macOS option-composition (<code>alt+1</code> → <code>¡</code>) can never mis-fire.</li>"
                  "<li><strong>Migration:</strong> every existing binding moves in (⌘K, ⌘J/⌘E/⌘Y/⌘U/⌘O/⌘I doors, ⌘[ ⌘] panel cycle, ⌘W, ⌘⇧P, <code>?</code> HUD). No other <code>addEventListener('keydown')</code> may claim a global combo.</li></ul>",
             criteria=["A table-driven test fails on a duplicate combo, and fails on a table action with no handler.",
                       "Every legacy binding still works (one test per binding).",
                       "The focus-scope matrix passes: text input, <code>contenteditable</code> (the Write editor), FloatMenu, a focused WorkspaceWindow (which owns ←/→), an open modal, and the arXiv iframe. Each has its expected behaviour asserted.",
                       "<code>git grep \"addEventListener('keydown'\"</code> outside the dispatcher shows only element-scoped handlers. List them in the handoff."],
             files=["apps/reading/src/components/hotkeys/keymap.ts (new)", "apps/reading/src/components/hotkeys/bindings.ts", "apps/reading/src/workspace/shortcuts.ts", "apps/reading/src/AppShell.tsx"]),
        dict(title="Key sheet (prefix+?) and aria-keyshortcuts from the same table",
             desc="Upgrade the existing <code>?</code> HUD into a key sheet rendered from <code>keymap.ts</code>: grouped by task, a <code>/</code> filter, the prefix form and the chord form side by side, with a close that returns focus. Every actionable control that has a binding gets <code>aria-keyshortcuts</code> generated from the table, never hand-written. The sheet is lazy-loaded.",
             criteria=["A test proves that no binding in the table is missing from the rendered sheet.",
                       "<code>build:check</code> headroom is no worse than the baseline minus 0.5 KB (the sheet is lazy).",
                       "The sheet has stories in light and dark, at 1280 and 390."],
             files=["apps/reading/src/components/hotkeys/KeySheet.tsx (new, lazy)", "apps/reading/src/components/hotkeys/HotkeysHud.tsx"]),
        dict(title="Rename ThreadBreadcrumb → Trail",
             desc="\"Thread\" must mean only a subagent investigation (glossary). ThreadBreadcrumb/ThreadJump are cross-workflow entity hops over GET <code>/thread/{node_id}</code>. Rename the components and their imports to <code>Trail</code>/<code>TrailJump</code>, with no behaviour change. Leave the backend route as is, and note it for lane B.",
             criteria=["tsc is clean, the suite passes, and <code>git grep ThreadBreadcrumb</code> finds nothing in apps/reading/src."],
             files=["apps/reading/src/components/ThreadBreadcrumb*.tsx → Trail*.tsx", "call sites"]),
        dict(title="Decision record: D2 supersedes SPR-08's no-leader rule",
             desc="Write <code>docs/decisions/mothership-keys-herdr-prefix.md</code>. It records what was decided (the prefix plus ctrl+alt chords), who decided it (the operator, 2026-09-24, DECISIONS.md D2), what was rejected (SPR-08's no-leader rule; plain alt chords because of macOS composition; ⌘⇧ letters only), and what would reverse it.",
             criteria=["The file exists, and the keymap table cites it on every row whose origin is D2."],
             files=["docs/decisions/mothership-keys-herdr-prefix.md (new)"]),
    ],
    rigor=dict(
        honesty="F1–F5 were proven by a grounding agent that bundled main's modules with esbuild under jsdom, using another worktree's node_modules. Your base is the design chain, and W3 rewrote AppShell. So re-prove each defect <em>on your base</em> before touching it. If one no longer reproduces, record \"fixed upstream by W3 &lt;sha&gt;\", never \"fixed\", and keep the test as a guard.",
        fairness="Steelman the rejected option in the handoff. It keeps SPR-08's no-leader rule and puts the mothership on the 22 free ⌘⇧+letter combos that the refuter found (MISS7). That means no mode to learn and one keystroke fewer. D2 still wins: the operator ruled it, herdr muscle memory is the point, and 22 letters cannot address 174 tabs, while a prefix plus the switcher can. Note who pays: the one-handed ⌘ user, now faced with a two-step prefix. That is why every prefix action also has a ctrl+alt chord.",
        rigor="Enumerate the focus contexts <em>before</em> writing the dispatcher: text input, <code>contenteditable</code> (tiptap), FloatMenu, a focused WorkspaceWindow, an open LemonModal, and the arXiv iframe (which cannot receive keys). Give each an expected outcome for prefix, chord and plain keys, and assert all of them in one table-driven test. The prefix has no timeout. It is armed until the next key or Esc, as in herdr, so the plan carries no invented millisecond number.",
        diligence="Read in full before editing: <code>bindings.ts</code> (including the SAFE_ASSIGNABLE range at :521-535 and the browser-reserved list at :438-462), <code>shortcuts.ts</code>, <code>AppShell.tsx</code>, <code>CommandPalette.tsx</code>, <code>HotkeysHud</code>, <code>WorkspaceWindow.tsx:172-215</code> (its own ←/→ ownership), and <code>AssignHotkey.tsx</code> (per-entity keys, unreachable today). Then run <code>git grep -n \"keydown\" apps/reading/src</code> and list every handler you migrate or deliberately leave element-scoped.",
        defensibility="<code>keymap.ts</code> is the only place a binding may be defined. Every row carries its origin (<code>herdr-default</code>, <code>D2</code> or <code>legacy-SPR-08</code>) and, for D2 rows, a link to <code>docs/decisions/mothership-keys-herdr-prefix.md</code> (milestone 7) and DECISIONS.md D2. A future maintainer asking \"why ctrl+alt and not alt?\" finds the macOS composition reason in the file itself, not in chat."),
    upstream=[("None in lane A", "wave 0"), ("Design chain W1+W3 (+W7) — pushed branches", "they rewrite the same shell files; base on them")],
    external=["Nothing from lane B.", "Node + npm to run <code>npm ci</code> in the worktree."],
    out_of_scope=["Workstations, tabs, the branch tree or the switcher's new kinds. Those are MS-03 and MS-04; this sprint only makes the keymap ready for them.",
                  "Restyling the palette, the HUD or the dock. W2 and W3 own the look; this sprint touches behaviour and the key sheet only.",
                  "Per-entity custom hotkeys (AssignHotkey). They remain unreachable until MS-03 gives them a namespace.",
                  "Changing the backend <code>/thread/{node_id}</code> route. The rename is frontend only."],
    gates=[("Typecheck", "npm --prefix <wt>/apps/reading run typecheck", "0 errors"),
           ("Full suite", "npm --prefix <wt>/apps/reading run test -- --no-color", "all pass; count at least baseline + new tests"),
           ("Defect proofs", "revert each F1–F5 fix by file copy and rerun its test", "each test fails on revert, then passes on restore"),
           ("Keymap integrity", "the vitest keymap table test (duplicates, missing handlers, focus matrix)", "pass"),
           ("Bundle", "npm --prefix <wt>/apps/reading run build:check", "within budget; headroom at least baseline − 0.5 KB"),
           ("Different-lineage critic", "codex exec … < /dev/null on the branch diff", "ACCEPT, or every finding fixed or answered")],
    next_when="MS-01's branch is pushed and its critic accepted. MS-03 and MS-04 base on it.",
    harness=dict(pattern="inline", unit="None: milestones 3–5 converge on AppShell and the keymap.",
                 why="One owning seam (the shell's key and layout lifecycle). A fan-out would collide in AppShell.tsx.",
                 lenses=["Does every F1–F5 test genuinely fail on the base? Rerun it against a clean checkout of the base SHA.",
                         "Can any key reach two handlers, or none? Fuzz the dispatcher with every table combo in every focus context."],
                 lenses_short=["F1-F5 tests fail on base", "no key reaches two handlers or none"]),
))

# ---------------------------------------------------------------- MS-02
SPRINTS.append(dict(
    id="MS-02", slug="craft-carry-over", wave=0, status="running (design workflow)", budget="workflow + train",
    owner="Antiek Nudge v2 (lane A)",
    title="Craft carry-over: land the design chain",
    tagline="Land the design waves that turn the audit's 50% baseline into a trustworthy base. Finish the three still in build.",
    context=(
        "<p><strong>What this sprint is about.</strong> The 2026-09-23 design audit scored the UI 24/48 (50%) against a floor of "
        "42/48, and two critical-failure vetoes failed. The baseline is <code>/Users/slimydog/.claude/jobs/236c36bd/tmp/design-audit/SCORE-BASELINE-full.md</code>. "
        "The design spec (\"Paper, ink, and one sun\") was then built in waves. Their state on 2026-09-24:</p>"
        "<ul>"
        "<li><strong>W1 tokens:</strong> <code>design/w1-tokens-foundation-20260923</code> at <code>7144b8e6b</code>. Axe dark 727→44, light 52→4; fonts ship; theme toggle.</li>"
        "<li><strong>W5 motion:</strong> <code>design/w5-motion-20260923</code> at <code>29fe3bde6</code>. Parallax 139→15.9 px; one rAF heartbeat.</li>"
        "<li><strong>W3 shell, states and prose:</strong> <code>design/w3-shell-states-prose-20260923</code> at <code>0d68b6213</code>. tsc 0, vitest 2506/2506, but only 60 B of entry headroom.</li>"
        "<li><strong>W7 crashes and vetoes:</strong> <code>design/w7-crashes-20260924</code> at <code>86a03898b</code>. Five false-zero pages fixed, the 768 px crash fixed, <code>/wrestle</code> deep links, story fixtures, and a lazy operator-pages split that frees about 2.2 KB.</li>"
        "<li><strong>W2 controls, W6 visual gates and W4 copy:</strong> being built by the design workflow <code>wf_7a06ae88-9fb</code>.</li>"
        "</ul>"),
    position="Wave 0, alongside MS-01. Every later sprint's craft bar assumes these waves have landed.",
    goal_line="W7 → W1 → W3 → W5 land through Antiek Nudge's train in that order (W7 first, because it frees the headroom W1 and W3 need). W2, W6 and W4 finish, pass their critics and are pushed.",
    goal=("<p>The order is set by the budget. W3 alone leaves 60 bytes of headroom, and W7's lazy operator pages free about 2.2 KB. "
          "When this sprint ends, main carries the tokens, the prose layer, the states primitives and the motion heartbeat that the "
          "mothership surfaces are built from.</p>"),
    milestones=[
        dict(title="Queue W7 first, then W1, W3, W5",
             desc="Give Antiek Nudge the order and the reason (headroom numbers). At each slot: merge main into the branch, rerun its gate, send the head.",
             criteria=["Each branch lands on main in that order (<code>git merge-base --is-ancestor</code>)."], files=[".lane/PR_BODY.md per branch"]),
        dict(title="W2 controls, W6 visual gates, W4 copy: finish in the design workflow",
             desc="The resumed workflow builds W2 and W6 on W1 and W4 on W3, with a critic loop and a ship step. W3's step verifies and completes the existing branch without rebuilding it.",
             criteria=["Each wave's ship result is gate-green and pushed.", "W6 adds the dark lostpixel axis and proves it catches a dark-only regression."],
             files=["see each wave's brief in the design workflow script"]),
        dict(title="Re-merge after each landing to keep headroom",
             desc="After W7 lands, W1 and W3 merge main and must show at least 1 KB of entry headroom. Anything short of that lazy-loads more; the budget is never raised.",
             criteria=["The <code>build:check</code> line is quoted for each re-merged head."], files=["(per branch)"]),
    ],
    rigor=dict(
        honesty="W3 was finished by a standalone builder after its workflow step died on the session limit. Its gate (2506/2506) was re-run by the orchestrator, but its critic loop never ran. Say so in W3's PR body, and do not present it as \"critic-accepted\" until a critic has actually run on <code>0d68b6213</code> or later.",
        fairness="Steelman landing W1+W3 first, since they are the foundation W7 builds on, and they merge cleanly with each other. It loses because W3 alone leaves 60 B of headroom. Any small change in between would redden the required tsc job, while W7 first frees about 2.2 KB. Record who pays for W7-first. W1 and W3 wait behind it in the train. W7 lands on a base without the tokens it was designed beside. Any conflict it creates is resolved on the W1/W3 re-merge, not on W7.",
        rigor="The W7 → W1 → W3 → W5 order is a claim about bytes, so check it at each step. After each landing, rebase every remaining wave on the new main and record the entry headroom <code>build:check</code> prints. Expected: about +2.2 KB after W7, then W1's cost (~0.9 KB), then W3 falling toward its 60 B. Assert that W1+W3 together still fit after W7, and that W5 fits after W3. Any negative is a stop, never a budget raise. W2/W6/W4 are this sprint's other milestone: each needs its critic verdict and pushed SHA quoted, and W6 needs its injected dark-only regression shown caught.",
        diligence="Before queuing, read each wave's <code>.lane/PR_BODY.md</code> and its NOT MEASURED section. Check with <code>git merge-tree</code> that each still merges cleanly with current main, because main moved twice overnight.",
        defensibility="The order and the headroom arithmetic go into each PR body, so the train's owner, or anyone later, can see why W7 went first."),
    upstream=[("None", "wave 0")],
    external=["Antiek Nudge's merge train (it owns update-branch and merge).", "The design workflow <code>wf_7a06ae88-9fb</code> for W2, W6 and W4."],
    out_of_scope=["New design work beyond the waves' briefs. That is what the mothership sprints are for.",
                  "Raising the bundle budget."],
    gates=[("Landed", "git merge-base --is-ancestor <wave-head> origin/main", "true for W7, W1, W3 and W5"),
           ("Headroom", "npm run build:check on each re-merged head", "≥ 1 KB after W7"),
           ("W6 dark axis", "lostpixel run with an injected dark-only regression", "caught, then reverted")],
    next_when="W7 and W1 are on main (MS-03 needs the tokens) and W3 is on main (MS-05 and MS-06 need the prose layer and states).",
    harness=dict(pattern="inline", unit="None: sequencing through the train is serial by nature.",
                 why="Merges are serial and train-owned; the wave builds run in their own workflow.",
                 lenses=["Is the landing order justified by measured headroom at each step, or only asserted?"],
                 lenses_short=["headroom measured at each landing"]),
))

# ---------------------------------------------------------------- MS-03
SPRINTS.append(dict(
    id="MS-03", slug="motherships-workstations", wave=1, status="specced", budget="9 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Motherships + workstations chassis",
    tagline="Three shells (Research, Writing, Reading) over the same projects, with switching that never loses your place, a switcher that finds anything, a sidebar of live threads, and an attention inbox.",
    context=(
        "<p><strong>What this sprint is about.</strong> The app has no project or workstation concept today (SW-01 ABSENT). "
        "<code>git grep</code> finds no activeProject, workstationStore or useWorkstation anywhere. Its four \"doors\" (Research ⌘J, Read ⌘E, "
        "Write ⌘Y, Speak ⌘U) each reset you to that workflow's default route. The operator's rulings:</p>"
        "<ul>"
        "<li><strong>D1/D5:</strong> three motherships (Research, Writing, Reading) over <em>shared</em> workstations, where a workstation is a project.</li>"
        "<li>Switching mothership keeps the workstation.</li>"
        "<li><strong>D4:</strong> an attention inbox.</li>"
        "</ul>"
        "<p>herdr's model is the reference (<code>research/</code>, <code>DESIGN-MODEL.md</code> §1). His live session has 20 workspaces and 252 tabs. "
        "Lane B owns the workstation registry, as edges and never copies, following <code>write_folders</code>. Until it lands, "
        "this sprint builds <strong>local-first</strong> against the contract shapes (<code>THREAD-CONTRACT.md</code> §2.1) and "
        "swaps the data source afterwards.</p>"
        "<p><strong>What to reuse, not rebuild:</strong></p>"
        "<ul>"
        "<li>the herdr attention P0 already on main (#3078: state registry, rollup, unseen axis, clickable toasts, <code>state:</code> chips)</li>"
        "<li>the open P1 and P2 PRs, #3088 (completion sound, window-title status) and #3092 (favicon dot, layout presets)</li>"
        "<li><code>/my-research</code> (MyResearch.tsx: families, attention, unseen)</li>"
        "<li><code>workspace/persistence.ts</code> scopes</li>"
        "</ul>"
        "<p><strong>Base:</strong> MS-01's branch. <strong>Branch:</strong> <code>design/mothership-03-chassis</code>.</p>"),
    position="Wave 1. It needs MS-01 (the keymap and a stable shell). MS-04 (tabs) and MS-05 (document door) sit inside the chassis it creates.",
    goal_line="The operator can open several workstations, hop between them and between the three motherships by prefix or chord without losing his place, find anything from one switcher, see live thread state in a sidebar, and read an attention inbox.",
    goal=("<p>Routes become <code>/w/:workstationId/:mothership/…</code>, where mothership is research, writing or reading, and the old routes stay as "
          "deep links that resolve into a workstation. Each open workstation keeps, per mothership, its last route and layout. The switcher "
          "(⌘K / <code>prefix+g</code>) searches workstations, their open tabs, documents and threads. The sidebar "
          "(<code>prefix+b</code>) lists workstations with rolled-up thread state. The inbox (<code>prefix+i</code>) lists what needs you.</p>"),
    milestones=[
        dict(title="Workstation store (local-first, contract-shaped)",
             desc="Add <code>src/workspace/workstations.ts</code>, a Zustand store of <code>{workstations: Workstation[], open: id[], activeId, activeMothership, perMothership: {research?, writing?, reading?: {route, layoutKey}}}</code> using the exact field names of THREAD-CONTRACT §2.1. It persists through <code>workspace/persistence.ts</code> under a new scope. A data-source adapter interface (<code>local</code> | <code>server</code>) lets lane B's registry swap in without a UI change.",
             criteria=["Unit tests for open, close, focus, reorder and archive.", "It persists across reload, and switching the adapter needs no component change (a test with a fake server adapter)."],
             files=["apps/reading/src/workspace/workstations.ts (new)", "apps/reading/src/workspace/persistence.ts"]),
        dict(title="Seed workstations from what exists",
             desc="Propose starter workstations from existing research families (<code>parent_investigation_id</code> roots) and from deliverables with <code>investigation_root_id</code>. Nothing is auto-created without the operator: a \"Create workstations from my research\" sheet lists them, and the operator accepts them.",
             criteria=["The sheet has designed states: loading, empty (\"No research yet\"), error with Retry, and ready.", "Nothing is written without an explicit accept."],
             files=["apps/reading/src/shell/WorkstationSeedSheet.tsx (new)"]),
        dict(title="Routing: /w/:id/:mothership/* with deep-link resolution",
             desc="Nest the existing route trees under the mothership. Every legacy route (for example <code>/inv/:id</code>, <code>/write/:id</code>, <code>/read/:id</code>) resolves into the active workstation, or asks which one to open in, and never 404s.",
             criteria=["A routing test covers every route in App.tsx: each resolves, and none renders twice.", "Browser back and forward move between workstations sensibly (tested)."],
             files=["apps/reading/src/App.tsx", "apps/reading/src/shell/*"]),
        dict(title="Mothership switch keeps the workstation (prefix+m / ctrl+alt+m)",
             desc="Research → Writing → Reading cycles inside the same workstation and restores that mothership's last route. <code>prefix+shift+m</code> opens a 3-way picker. The NavRail doors become mothership doors scoped to the active workstation. Speak remains its own door, outside the three motherships.",
             criteria=["Switch-and-return lands on the exact prior route in each mothership (test).", "Every door has a visible, labelled current state (<code>aria-current</code>)."],
             files=["apps/reading/src/shell/NavRail.tsx", "apps/reading/src/shell/SceneChrome.tsx"]),
        dict(title="Switcher: workstations, tabs, documents, threads",
             desc="Extend the fixed ⌘K palette with workstation, open-tab, document and thread kinds, each with a match reason (frontend-craft §4). It also accepts a hierarchical tab number, <code>3.2.1</code>, whose resolution MS-04 supplies. Scoring by result tier: exact id or title, then prefix, then fuzzy.",
             criteria=["A test fixture of 20 workstations and 252 tabs: an exact title is first, and fuzzy matches are labelled as suggestions.", "p95 query time is under 100 ms on that fixture (measured in the test)."],
             files=["apps/reading/src/components/CommandPalette.tsx"]),
        dict(title="Shell sidebar with live thread state (prefix+b)",
             desc="Build an always-available sidebar: workstations first, with rolled-up counts (running, needs-you, unseen), then the active workstation's live threads with state and spend. Reuse MyResearch's grouping and the #3078 registry. Collapsed by default below 1024 px.",
             criteria=["No count or state is invented: an unknown shows \"—\", and a failed fetch shows an honest error (the W7 rule).", "Stories: light and dark, 1280 and 390, with loading, error and ready states."],
             files=["apps/reading/src/shell/Sidebar.tsx (new, lazy)"]),
        dict(title="Attention inbox surface (prefix+i)",
             desc="An inbox listing pending attention (thread done, needs you, and later D4 kinds), ordered like the operator's herdr ask-inbox: pending questions first. Land P1 #3088 (sound, title count) and P2 #3092 (favicon dot) work here, re-based rather than rewritten.",
             criteria=["Items open their target, and focus returns to the inbox on close.", "The document title shows a count; the favicon dot reflects the unseen state (tests)."],
             files=["apps/reading/src/shell/Inbox.tsx (new, lazy)", "apps/reading/src/shell/attention/*"]),
        dict(title="Session restore",
             desc="Open workstations, the active one, and each mothership's last route survive a reload through the local adapter, and follow the operator across devices once lane B's session store exists. A pending server session is never shown as restored.",
             criteria=["A reload restores exactly (test).", "The server adapter is covered by the fake-adapter test; the real one is NOT RUN until lane B lands, and the handoff says so."],
             files=["apps/reading/src/workspace/workstations.ts"]),
        dict(title="Bundle + critic",
             desc="Sidebar, inbox and seed sheet are lazy. Keep the entry under budget.",
             criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."],
             files=[]),
    ],
    rigor=dict(
        honesty="The server side of workstations and sessions belongs to lane B and may not exist when you finish. Everything you prove against the fake adapter is \"contract-shaped, local\", not \"synced\". The handoff must separate the two, and the UI must never say \"saved to your account\" while only localStorage is in play.",
        fairness="Steelman one workstation holding Research and Writing tabs side by side, the option recommended in the interview. It needs fewer concepts and one tab strip. The operator ruled for three motherships (D1/D5), and his standing \"net-new, not merged\" Write-canvas choice points the same way. Record who pays for the three-shell choice: the person who wants to glance at research while writing. They are served by MS-05's docked reader pane, not by merging the shells.",
        rigor="Routing is the dangerous part, and it needs two assertions. (a) Every route in <code>App.tsx</code> (about 60 today) except <code>/login</code> and <code>/_panel/:panelId</code> resolves under <code>/w/:id/:mothership</code>, renders once and keeps its params. (b) Those two resolve <em>outside</em> the tree. Add the switch round trip: after research → writing → research, <code>perMothership.research.route</code> and its layout key equal their values before the switch.",
        diligence="Read <code>MyResearch.tsx</code> (grouping, attention, unseen), the #3078 attention registry, the #3088 and #3092 diffs (<code>gh pr diff</code>), <code>workspace/persistence.ts</code>, <code>NavRail</code>, <code>SceneChrome</code> and <code>workflowTaxonomy.ts</code> before writing a line. The sidebar and inbox must extend those, never re-implement them.",
        defensibility="The data-source adapter interface is the seam lane B plugs into. Document it at the top of <code>workstations.ts</code> with the contract section it mirrors (§2.1), so when lane B's registry lands, the swap is one file and nobody redesigns the UI. Contract §2.1 is unsigned as of 2026-09-24. A field rename by lane B voids the one-file-swap claim until both lanes sign, so record the adapter-seam decision in DECISIONS.md as well."),
    upstream=[("MS-01", "one keymap owner (prefix+m/b/g/i) and a stable AppShell"), ("MS-02 (W7, W1 on main)", "tokens and headroom")],
    external=["Lane B: workstation registry, session store, and a thread-by-owner/state list endpoint. Built against the contract shape until they exist.", "THREAD-CONTRACT.md signed by both lanes."],
    out_of_scope=["Tabs and the branch tree (MS-04). The chassis holds a single route per mothership until MS-04 lands.",
                  "Reading any document in place (MS-05).",
                  "Server persistence of workstations. That is lane B's; this sprint only calls it through the adapter."],
    gates=[("Typecheck + suite", "npm run typecheck && npm run test -- --no-color", "0 errors; all pass"),
           ("Route coverage", "the vitest route-table test", "every App.tsx route resolves once under /w/:id/:mothership"),
           ("Switcher scale", "the vitest 20×252 fixture test", "p95 < 100 ms; the exact title ranks first"),
           ("States", "Storybook stories for sidebar, inbox and seed sheet in light and dark at 1280 and 390", "every state rendered; no invented zero"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="The chassis branch is pushed and accepted. MS-04 and MS-05 base on it.",
    harness=dict(pattern="inline", unit="None: routing, store and switcher interlock through App.tsx and the store.",
                 why="Milestones share App.tsx and workstations.ts.",
                 lenses=["Does any legacy deep link break or render twice under /w/:id/:mothership?",
                         "Does the UI ever claim server persistence while only the local adapter ran?"],
                 lenses_short=["legacy deep links resolve once", "no false 'synced' claim"]),
))

# ---------------------------------------------------------------- MS-04
SPRINTS.append(dict(
    id="MS-04", slug="branch-tab-tree", wave=1, status="specced", budget="8 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Branch tab tree (the signature)",
    tagline="Tabs that grow as the operator's logic tree, nested without limit, and legible at 174 tabs.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator (D6, 2026-09-24): sub-branches from sub-branches should be "
        "\"infinitely layered to represent the precision of the logic tree\". Opening a footnote, reference, citation, island or deep research "
        "from a tab spawns a <em>child</em> tab. There is no tab concept on main at all (SW-03, N4). The only unbounded tree on main is the "
        "investigation tree (<code>parent_investigation_id</code> → the recursive <code>InvestigationSidebar</code>), which is the model to "
        "follow.</p>"
        "<p><strong>Tab ≠ branch</strong> (agreed with lane B). The tab tree is <em>navigation state</em>, server-side per account through the "
        "single-writer API. The research branch is <em>provenance</em>, written to the parent investigation's log before the child starts. "
        "Pruning a tab never deletes a branch. The design is in <code>DESIGN-MODEL.md</code> §2a:</p>"
        "<ul>"
        "<li>a path header, compressed in the middle past about four crumbs</li>"
        "<li>a sibling strip with a <code>↳ n</code> child chip</li>"
        "<li>a tree panel with a six-level indent cap, a depth badge and subtree focus</li>"
        "<li>hierarchical numbers used as addresses (<code>3.2.1</code>)</li>"
        "<li>keys <code>prefix+u/o/n/p/t</code></li>"
        "<li>prune by default, or close-only-this, with 10 s undo</li>"
        "</ul>"
        "<p>This is the design's single signature element. Spend boldness here and keep everything around it quiet.</p>"
        "<p><strong>Base:</strong> MS-03. <strong>Branch:</strong> <code>design/mothership-04-branch-tree</code>.</p>"),
    position="Wave 1, after MS-03. MS-05 (a document opened from a citation becomes a child tab) and MS-06 (Reading's rabbit holes) depend on it.",
    goal_line="Every mothership holds a forest of branch tabs per workstation. Any depth is reachable in two keystrokes by number, and the tree stays legible and fast at the operator's real scale.",
    goal=("<p>The fixture is his herdr scale: 20 workstations, one with 174 tabs, and depth greater than 12 in at least one branch. A tab "
          "records its parent, its branch origin (the passage it was opened from) and its stable hierarchical number. The UI makes the "
          "tree the thing you steer by: the path to where you are, your siblings, and the whole tree on demand.</p>"),
    milestones=[
        dict(title="Tab tree model (contract §2.2), local-first",
             desc="A tab-tree store: <code>{tab_id, parent_tab_id, branch_origin{doc_id,locator,kind}, hier_number, child_order, last_visited_child_id, pruned_at, kind, ref, mothership}</code>. Numbers are stable, never reused under the same parent, and never renumbered. It persists through an adapter: an in-memory implementation now, and lane B's tab-tree API (§1.6) once W1 ships, following the same adapter pattern as MS-03. Tab state never goes to <code>localStorage</code> or <code>sessionStorage</code> (§1.6).",
             criteria=["Property tests: numbers stay unique and stable under random spawn, prune, lift and undo sequences (≥ 1,000 generated sequences).", "Depth is unbounded (a test at depth 200)."],
             files=["apps/reading/src/workspace/tabTree.ts (new)"]),
        dict(title="Spawn a child tab from any passage",
             desc="One <code>spawnChild(parentTab, origin, kind, ref)</code> used by every \"open from here\" path that MS-05, MS-06 and MS-07 will call. For now, wire it from the existing openers: ChunkModal citations, the DRW evidence reader window, TalkToBook and MetaReading citation jumps.",
             criteria=["Each wired opener creates a child with the correct <code>branch_origin</code> (tests).", "Opening from a citation does NOT move the target book's saved position (this fixes the clobbering in R4)."],
             files=["apps/reading/src/workspace/tabTree.ts", "openers at their call sites"]),
        dict(title="Path header",
             desc="The root → current path. Every crumb is a link, and past about four crumbs the middle compresses to an ellipsis that opens the full path. At 390 px it shows only the current tab plus a back affordance.",
             criteria=["Stories at depth 1, 4, 12 and 40 in light and dark at 1280 and 390, with no overflow and no horizontal scroll.", "Keyboard: every crumb is reachable, and Esc closes the expanded path, returning focus."],
             files=["apps/reading/src/shell/tabs/PathHeader.tsx (new)"]),
        dict(title="Sibling strip",
             desc="The current tab's siblings, herdr-style, with a <code>↳ n</code> child chip and overflow into a searchable menu when the siblings exceed the strip width.",
             criteria=["174 siblings do not break the layout, and the overflow menu is searchable (story + test)."],
             files=["apps/reading/src/shell/tabs/SiblingStrip.tsx (new)"]),
        dict(title="Tree panel (the signature) — prefix+t / ctrl+alt+y",
             desc="The whole forest as an outline:<ul><li>hierarchical numbers and a glyph per surface kind</li><li>live state on thread tabs, and an unseen dot</li><li>indent capped at 6 levels, with deeper nodes carrying a depth badge</li><li>focus-subtree re-roots the panel, and up restores it</li><li>virtualised</li><li>arrow keys move, Enter opens, and <code>←</code>/<code>→</code> collapse and expand (a tree-view ARIA pattern)</li></ul>",
             criteria=["Renders 174 nodes at 60 fps while scrolling (measured with the Performance API in a Playwright run, or NOT MEASURED with the reason).", "It passes the ARIA tree pattern checks (role=tree/treeitem, aria-level, aria-expanded); tested.", "Stories: empty, 1 node, 174 nodes, depth 40, and running/needs-you states."],
             files=["apps/reading/src/shell/tabs/TreePanel.tsx (new, lazy)"]),
        dict(title="Numbers as addresses + tree keys",
             desc="The switcher (MS-03) resolves <code>3.2.1</code> to a tab. <code>prefix+1..9</code> reaches root tabs, <code>prefix+u</code> the parent (returning to the exact origin locator), <code>prefix+o</code> the last-visited child, and <code>prefix+n/p</code> the next/previous sibling. The chord twins come from MS-01's table. <code>ctrl+alt+t</code> is Ubuntu/Fedora's launch-terminal key, so give tree-panel the chord <code>ctrl+alt+y</code>, recording why in the table.",
             criteria=["Keyboard tests for every tree key, including focus return and the exact-locator return on <code>prefix+u</code>."],
             files=["apps/reading/src/components/hotkeys/keymap.ts"]),
        dict(title="Prune / close-only-this with undo",
             desc="Close offers prune (the default: the tab and its subtree) or close-only-this (children lift to the parent). Both can be undone for 10 s. On main, LemonToast has no action slot (its lifetimes are 4/6/8 s), so this milestone adds an undo action with a 10 000 ms lifetime. If W2 added a toast action first, reuse it. Pruned subtrees stay in history; branches are never deleted.",
             criteria=["Tests: prune+undo restores numbers exactly, lift keeps children's numbers stable, and a pruned research tab's investigation is untouched.", "No confirmation dialog: undo is the safety, as in herdr's close-tab."],
             files=["apps/reading/src/workspace/tabTree.ts", "apps/reading/src/shell/tabs/*"]),
        dict(title="Scale proof + critic",
             desc="Render the operator's herdr-scale fixture (20 workstations, 252 tabs, one 174-tab tree, a branch deeper than 12) as a rendered walkthrough.",
             criteria=["Screenshots in light and dark at 1280 and 390 are saved under <code>.lane/shots/</code> and listed in the PR body.", "<code>build:check</code> within budget (the tree panel is lazy).", "Codex critic ACCEPT."],
             files=[".lane/shots/*"]),
    ],
    rigor=dict(
        honesty="\"Unbounded depth\" is easy to claim and hard to prove. The proof is a test at depth 200, plus a rendered tree panel at depth 40. If virtualisation or indentation degrades somewhere (say depth 60), report the measured limit. Do not write \"infinite\".",
        fairness="Steelman herdr's flat tabs, the operator's current tool. They offer zero learning curve and one strip. The tree wins because a rabbit hole <em>is</em> a tree, and he asked for it explicitly (D6). The cost falls on the shallow Writing user, who sees a tree where a strip would do. The sibling strip is exactly that strip, so a depth-1 tree looks like herdr.",
        rigor="Enumerate the number invariants before coding: unique, stable, never reused under a parent, and surviving prune, lift and undo. Encode them two ways. First, enumerate exhaustively every sequence of length ≤ 6 over the four operations (4⁶ + … + 4 = 5,460 sequences). Then run seeded property tests (fast-check, fixed seed, shrinking on failure) over longer sequences with depth up to 200. Record the seed and the sequence-length bound in the test file.",
        diligence="Read the investigation tree's recursion (<code>InvestigationSidebar</code>) and <code>parent_investigation_id</code> handling, and reuse its rendering approach. Read <code>windowsStore.ts</code> (8 windows, memory-only) to understand why it is <em>not</em> the tab system: that choice is recorded in the master spec's rejected alternatives. Read <code>components/lemon/LemonToast.tsx</code>: on main its lifetimes are 4000/6000/8000 ms and it has <em>no</em> action or undo slot. Milestone 7 therefore adds an undo action with a 10 000 ms lifetime. Pruning is the most destructive navigation act, so it outlives the longest existing toast (8 s) by the time it takes to read the pruned-subtree summary. Record that reasoning at the constant. If W2's controls wave adds a toast action first, reuse it and cite its branch.",
        defensibility="The tab tree and the research branch are separate records. Put a comment at the top of <code>tabTree.ts</code> saying so, and linking THREAD-CONTRACT §2.2, so nobody later \"simplifies\" by deleting a branch when a tab is pruned. Point it at the M7 regression test by name (\"a pruned research tab's investigation is untouched\"). The tab ≠ branch rule must also be in the signed contract before merge."),
    upstream=[("MS-03", "the chassis: workstations, motherships, switcher"), ("MS-01", "the keymap")],
    external=["Lane B: the server-side tab tree per account (contract §2.2). Built against the shape until it exists.", "Playwright (Chrome) for the scroll-fps measurement; if it can't launch, NOT MEASURED."],
    out_of_scope=["What a reader, footnote or island shows inside a tab (MS-05, MS-06, MS-07). This sprint moves tabs, not their content.",
                  "Arbitrary pane splits (rejected in the master spec).",
                  "Drag-to-reparent tabs. Tempting, but not asked for; note it as a follow-up."],
    gates=[("Property tests", "vitest tabTree property suite", "≥ 1,000 sequences, 0 invariant violations"),
           ("Depth", "vitest depth-200 test + depth-40 story", "pass; renders without overflow"),
           ("Keyboard + ARIA", "vitest tree keys + ARIA tree pattern", "pass"),
           ("Scale walkthrough", "rendered fixture screenshots", "saved and listed; light/dark at 1280/390"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="The tab tree is pushed and accepted, so MS-05/06/07 have spawnChild to call.",
    harness=dict(pattern="perspective-diverse-verify", unit="Build inline. Verify with distinct lenses.",
                 why="The build is one seam (tabTree.ts). The risk is in correctness and legibility, so verification gets diverse lenses.",
                 lenses=["Numbers-as-addresses: can any sequence of spawn, prune, lift and undo reuse or renumber a tab?",
                         "Legibility at depth: at depth 40 and 174 siblings, can a keyboard-only user still find the parent and return to the exact passage?"],
                 lenses_short=["numbers never reused or renumbered", "legible and reachable at depth 40 / 174 siblings"]),
))

# ---------------------------------------------------------------- MS-05
SPRINTS.append(dict(
    id="MS-05", slug="document-door-reader-pane", wave=1, status="specced", budget="7 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="One document door + reader pane",
    tagline="Any evidence opens in place: in a child tab or in the docked pane beside what you are writing or researching. Never a navigation away.",
    context=(
        "<p><strong>What this sprint is about.</strong> Every door into a document opens it differently today (RE-02..RE-10). Most do a "
        "full-page navigate that loses your place. The reader opens only documents with a <code>book_assets</code> row, so web and URL "
        "ingests 404 (F8). There is no reader pane in Research (<code>/inv/:id</code>) or in Writing.</p>"
        "<p>The Unified Reader spec (<code>/Users/slimydog/Antiek/specs/antiek-reader</code>) planned one resolver, "
        "<code>openDocument(id, opts)</code>. It never reached main: it exists only on "
        "<code>origin/snapshot/2026-09-21/detached/antiek-rebase-preflight</code>, together with a rich-block <code>Reader.tsx</code>. "
        "<strong>Salvage it, don't rewrite it.</strong></p>"
        "<p>Reader windows (#3384) and <code>WINDOW_PAGES.reader</code> exist and should be reused. A tab may carry at most one docked pane "
        "beside its main surface (master spec decision).</p>"
        "<p><strong>Base:</strong> MS-04 (it calls <code>spawnChild</code>). <strong>Branch:</strong> <code>design/mothership-05-doc-door</code>.</p>"),
    position="Wave 1, after MS-04. MS-06 (the Reading mothership) and MS-07 (islands) open documents through this door.",
    goal_line="One function, openDocument(id,{where: child_tab|pane|window, at: locator}), is the only way anything in the app opens a document, and it never navigates away from the workstation.",
    goal=("<p>Every door routes through it: citations, claims, source cards, notebook blocks, DocumentsIndex, Library, ⌘K and DRW "
          "evidence. In Research and Writing the reader docks as the pane beside the main surface, so the operator reads while he writes. "
          "Opening at a citation lands on that passage without moving the book's saved position.</p>"),
    milestones=[
        dict(title="Salvage openDocument + Reader.tsx from the snapshot branch",
             desc="<code>git show origin/snapshot/2026-09-21/detached/antiek-rebase-preflight:&lt;path&gt;</code> for the resolver and the rich Reader. Port them onto current main's APIs. List every divergence and why.",
             criteria=["The port compiles and its original tests (if any) pass, or are adapted with the reason recorded.", "The handoff lists which snapshot files were ported, which were dropped, and why."],
             files=["apps/reading/src/lib/openDocument.ts (new/ported)", "apps/reading/src/components/reader/Reader.tsx (ported)"]),
        dict(title="openDocument / openEvidence as the only door",
             desc="Route every door through it: ChunkModal, MasterMdViewer named sources, Write citation chips, AutoNotebook, ProjectTree, ⌘K, DocumentsIndex rows, Library cards and DRW evidence. <code>where</code> defaults to <code>child_tab</code> from inside a tab, and to <code>pane</code> from Writing.",
             criteria=["<code>git grep</code> finds no remaining <code>navigate('/read/</code> or <code>navigate(`/read/</code> outside openDocument (listed in the handoff).", "A test per door shows the right <code>where</code>."],
             files=["call sites across apps/reading/src"]),
        dict(title="Reader as the docked pane (Research + Writing)",
             desc="Register a Reader PanelKind for the docked pane. From Writing, a citation chip opens the source beside the draft at the cited chunk. From Research (<code>/inv/:id</code>), evidence opens beside the canvas.",
             criteria=["Stories and tests for both motherships. The pane never covers the main surface; at 390 px it becomes a sheet.", "Focus returns to the citation on close."],
             files=["apps/reading/src/workspace/PanelRegistry.tsx", "apps/reading/src/modes/Write/*", "apps/reading/src/modes/ResearchWorkstation/*"]),
        dict(title="Open at a passage without clobbering position",
             desc="Opening at a citation passes <code>at: locator</code>. The reader scrolls there and highlights the passage, and the book's saved position is untouched (this fixes R4's clobbering and MISS6's shared key). Per-pane reading focus replaces reliance on the global <code>readingFocus</code> bus (MISS3).",
             criteria=["A test: open book X at page 40 from a citation, close it, open X normally, and it resumes the original saved page.", "Two readers open at once each keep their own focus (test)."],
             files=["apps/reading/src/modes/Reading/usePosition.ts", "apps/reading/src/lib/readingFocus.ts"]),
        dict(title="Non-book documents: honest state until lane B serves them",
             desc="Web and URL ingests, <code>/ingest/asset</code> conversions and DRW web evidence 404 in the reader today (F8). Until lane B serves them, openDocument shows a designed state: the title, the source URL, and \"Antiek hasn't stored a readable copy yet\", offering the original link. It never shows a blank or a raw 404.",
             criteria=["A story and a test for that state.", "The state lists what lane B must serve, as contract fields."],
             files=["apps/reading/src/components/reader/NotStoredYet.tsx (new)"]),
        dict(title="Retire the dead doors",
             desc="DocumentsIndex rows go to the reader, not <code>/wrestle</code> (RE-05). The Read tab 'Library' pointing at <code>/wrestle</code> (MISS9) is fixed. <code>/wrestle</code> stays only as the bring-your-own-PDF tool.",
             criteria=["Route and tab tests.", "No view tab points at the wrong route (tested against workflowTaxonomy)."],
             files=["apps/reading/src/modes/DocumentsIndex/index.tsx", "apps/reading/src/shell/SceneChrome.tsx", "apps/reading/src/shell/workflowTaxonomy.ts"]),
        dict(title="Bundle + critic",
             desc="The ported Reader and the pane are lazy.",
             criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."],
             files=[]),
    ],
    rigor=dict(
        honesty="<code>origin/snapshot/2026-09-21/detached/antiek-rebase-preflight</code> was stranded by a rebase. Its <code>openDocument</code> resolver and rich <code>Reader.tsx</code> may depend on APIs that have since changed on main. Every ported file gets a ledger line in the handoff: ported as is, adapted (how), or dropped (why), each citing the main SHA it was diffed against. Do not present a salvage as new work, or new work as a salvage.",
        fairness="Steelman writing a fresh <code>openDocument</code>. The code would be smaller and would fit the new tab model, without archaeology. It loses to the P0 clause (\"avoid parallel substitutes for the reader\") and to the Unified Reader spec's already-reviewed design. Who pays: this sprint's builder pays the porting time once. MS-06 to MS-09, which all call <code>openDocument(id,{where,at})</code>, inherit any quirks of the adapted API. The operator gets no new reading capability this sprint beyond the door itself.",
        rigor="The door inventory is mechanical. Use <code>git grep -E</code> (no <code>\\b</code>: POSIX ERE silently ignores it) for <code>navigate(`/read/</code>, <code>navigate('/read/</code>, <code>&lt;Link to=…/read/</code>, <code>href=\"/read/</code>, every <code>openWindow('reader'</code>, every <code>window.open</code> of a document, and every route to <code>/wrestle</code> from DocumentsIndex or the Read tab (RE-05, MISS9). Record the origin/main counts as the \"before\" number and the after list in the handoff. A door the grep missed still navigates away.",
        diligence="Before porting, run <code>git diff origin/main...origin/snapshot/2026-09-21/detached/antiek-rebase-preflight</code> on the Reader and openDocument files. Read <code>antiek-reader</code>'s planned resolver contract, and <code>openWindow.ts</code> (the window policy and out-of-contract pages). Also read <code>usePosition.ts:14,18,53</code> (the shared sessionStorage key behind MISS6 and the R4 clobber that M4 fixes) and <code>readingFocus.ts</code> (the MISS3 global bus).",
        defensibility="openDocument's options (<code>where</code>, <code>at</code>) are the contract every later sprint calls. Document each option's default and the reason at the definition. A guard test enforces \"never navigate away\". It matches the same patterns as the inventory, allows zero occurrences outside openDocument, and is proven live by adding one mutant call and watching it fail. Record the <code>where</code>/<code>at</code> defaults in DECISIONS.md so later sprints can rely on them."),
    upstream=[("MS-04", "spawnChild and tabs"), ("MS-03", "the workstation and mothership context"), ("MS-02 (W3 on main)", "the prose layer and states primitives")],
    external=["Lane B: serve non-book documents (F8) and durable reading position (R4). An honest state stands in until then.", "The snapshot branch <code>origin/snapshot/2026-09-21/detached/antiek-rebase-preflight</code>."],
    out_of_scope=["Kindle-grade reading comfort (page keys, Aa, focus mode). That is MS-06.",
                  "Islands on the reader. That is MS-07.",
                  "Serving non-book documents from the backend. That is lane B."],
    gates=[("No navigate-away", "a vitest lint test over apps/reading/src", "0 direct reader-route navigations outside openDocument"),
           ("Position integrity", "vitest open-at-citation then resume", "the saved page is untouched"),
           ("Pane", "stories + tests in Research and Writing, at 1280 and 390", "never covers the main surface; focus returns"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="openDocument is the only door, so MS-06 and MS-07 build on it.",
    harness=dict(pattern="inline", unit="None: the door inventory touches many files but is one change (the resolver) threaded through them.",
                 why="The resolver is the single owning seam. Parallel builders would collide on shared call-site files.",
                 lenses=["Is there any remaining path that opens a document by navigating away, or that moves a book's saved position on a citation open?"],
                 lenses_short=["no navigate-away; no position clobber"]),
))

# ---------------------------------------------------------------- MS-06
SPRINTS.append(dict(
    id="MS-06", slug="reading-mothership", wave=2, status="specced", budget="8 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Reading mothership",
    tagline="A home that asks what you want to read, a reader good enough to replace a Kindle, and footnotes and references that open as branches instead of taking you away.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator (D5, 2026-09-24) wants a Reading mothership for two uses:</p>"
        "<ul>"
        "<li><strong>(i)</strong> a Kindle or real-book replacement, where companion deep researches, footnotes and references open in tabs, so he can "
        "\"tunnel through a rabbit hole and open many documents in the tabs\";</li>"
        "<li><strong>(ii)</strong> reading as the entry into a research or writing project: something specific, something he or an agent "
        "flagged, or something new.</li>"
        "</ul>"
        "<p>Grounding (<code>ground/lane-a-reading-mothership.json</code>, refuted MOSTLY_RELIABLE) found the reader short of a Kindle in five ways:</p>"
        "<ul>"
        "<li>no page keys (R2)</li>"
        "<li>no Aa control (R7)</li>"
        "<li>no focus mode (R5)</li>"
        "<li>position only in sessionStorage, per tab, and clobbered when a citation opens the book (R4)</li>"
        "<li>OS-only dark mode (R6)</li>"
        "</ul>"
        "<p>It also found that footnotes are deleted at ingest or left as dead text (F1), that in-body links navigate the whole app away (F2, ABSENT), "
        "and that there is no Continue or To-read door (H1, H2, T2, T3).</p>"
        "<p><strong>What to reuse:</strong></p>"
        "<ul>"
        "<li><code>/readings</code> PersonalSpace (dwell history), which feeds Continue</li>"
        "<li>the per-book thread <code>read-&lt;documentId&gt;</code></li>"
        "<li>passage notes</li>"
        "<li>W3's <code>.prose-antiek</code> layer</li>"
        "<li>the ported rich <code>Reader.tsx</code> from MS-05</li>"
        "</ul>"
        "<p><strong>Base:</strong> MS-05. <strong>Branch:</strong> <code>design/mothership-06-reading</code>.</p>"),
    position="Wave 2. It needs MS-04 (child tabs), MS-05 (openDocument and the ported Reader), and lane B's to-read flags plus durable position. Until those land it builds against contract §2.9.",
    goal_line="Opening the Reading mothership asks what to read: Continue, To read, or New. Reading feels like a good e-reader, and every footnote, reference and citation opens as a child tab you can return from to the exact passage.",
    goal=("<p>Kindle-grade here means:</p>"
          "<ul>"
          "<li>a 60–72ch measure in Charter</li>"
          "<li>page turns on ←/→ and space</li>"
          "<li>visible progress</li>"
          "<li>text size and line height</li>"
          "<li>day, night and paper themes</li>"
          "<li>no layout shift while loading</li>"
          "<li>a distraction-free mode (<code>prefix+f</code>) that leaves only the path header</li>"
          "</ul>"
          "<p>The rabbit hole is the branch tree from MS-04. The Continue door resumes the exact passage on any device once lane B's position record exists.</p>"),
    milestones=[
        dict(title="Reading home: three doors",
             desc="<code>/w/:id/reading</code> home. <strong>Continue</strong>: documents in progress, with position and progress, from lane B's position record, falling back to local position plus <code>/readings</code> dwell history. <strong>To read</strong>: <code>intent: read</code> flags, each showing who set it (user or agent), why, and for which workstation. <strong>New</strong>: library, search, import.",
             criteria=["Every door has loading, empty (truthful: \"Nothing waiting\" only after a real answer), error with Retry, and ready states (stories: light/dark, 1280/390).", "An agent-set flag is visibly distinguished from a user-set one (label + icon, never colour alone)."],
             files=["apps/reading/src/modes/ReadingHome/* (new, lazy)"]),
        dict(title="Kindle-grade reader: keys, progress, Aa, themes, stability",
             desc="Page keys (←/→, space, PgUp/PgDn, Home/End) in a reader key scope inside MS-01's keymap. They never fire in inputs or FloatMenu, and they defer to a focused WorkspaceWindow, which owns ←/→ (MISS5). Also: a progress bar with % and chapter-remaining; an Aa control (size, line height, margins; pagination is size-independent per the <code>usePosition</code> docblock); day, night and paper themes on the W1 tokens; and a skeleton shaped like the final TOC and column.",
             criteria=["Key-scope tests: keys work when the reader has focus and are inert in inputs, FloatMenu and focused windows.", "Measure: the rendered line is 60–72 characters at the default size (measured in a story test).", "Theme contrast is AA in all three themes (the tokens contrast test is extended)."],
             files=["apps/reading/src/modes/Reading/*", "apps/reading/src/components/reader/*"]),
        dict(title="Distraction-free mode (prefix+f)",
             desc="Hides NavRail, docks, the mascot, rails and ads, leaving the path header and the column. It is reversible with the same key or Esc, and the choice is remembered per document.",
             criteria=["Chrome occupancy at 844 px tall drops from about 35–42% to under 10% (measured in a story).", "The ad-frame attribution hooks are untouched when ads are shown (the existing ad tests pass)."],
             files=["apps/reading/src/modes/Reading/FocusMode.tsx (new)"]),
        dict(title="Footnotes and endnotes in place",
             desc="For documents whose ingest keeps structured notes (lane B), a note reference opens a popover in place, anchored to the marker and closable with Esc. \"Open as tab\" spawns a child tab at the note. For the legacy text-only case, notes are detected in the text; detection happens in the UI and never rewrites the stored document.",
             criteria=["Stories: a footnote popover, an endnote at the end of a chapter, and a note on another page window (the <code>paginate()</code> split).", "Tests: Esc returns focus to the marker, and \"Open as tab\" creates a child with <code>branch_origin.kind = footnote</code>."],
             files=["apps/reading/src/components/reader/Footnote*.tsx (new)"]),
        dict(title="Every in-body link becomes a branch, never a navigation",
             desc="Intercept clicks on links in the reader body (F2). An internal document opens through <code>openDocument(id,{where:'child_tab', at})</code>. A DOI or arXiv reference opens a \"resolve reference\" state (in the graph → open; else a rights-aware \"ingest?\" offer from lane B). External web links get an explicit \"open outside Antiek\" confirmation.",
             criteria=["A test: clicking a body link never changes <code>location.pathname</code> outside the workstation.", "The resolve-reference state machine has a story for each state: found, not stored (offer), rights-blocked (honest reason), failed."],
             files=["apps/reading/src/components/reader/BodyLinks.ts (new)"]),
        dict(title="Return to the exact passage",
             desc="<code>prefix+u</code> from any child tab returns to the parent at its <code>branch_origin.locator</code>, scrolls there and briefly marks the passage. The mark respects reduced motion.",
             criteria=["A test: open a footnote as a tab, go three levels deep, <code>prefix+u</code> ×3, and you land on the original passage."],
             files=["apps/reading/src/workspace/tabTree.ts", "apps/reading/src/components/reader/*"]),
        dict(title="Standalone books (use case i)",
             desc="Opening a book outside any project creates or uses its own reading workstation, per Q-A5 (lane B's <code>kind: reading</code>). \"Add to project…\" links it into a project later, and its branch tree and threads come along.",
             criteria=["A test with the local adapter; the server path is NOT RUN until lane B lands, and the handoff says so."],
             files=["apps/reading/src/workspace/workstations.ts"]),
        dict(title="Bundle, stories, critic",
             desc="Reading home and focus mode are lazy. Stories for every state.",
             criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."], files=[]),
    ],
    rigor=dict(
        honesty="\"Kindle-grade\" invites adjectives, so every claim is one of these numbers:<ul><li>60–72 characters per line at the default size</li><li>under 10% chrome at 844 px tall in <code>prefix+f</code> mode (today 35–42%)</li><li>AA contrast in day, night and paper</li><li>CLS ≈ 0 in the load story</li><li>←/→/space inert in inputs and FloatMenu (the key-scope matrix)</li></ul>Anything unmeasured is written NOT MEASURED; never write \"feels like a Kindle\".",
        fairness="Steelman keeping footnotes as plain popovers with no tabs: simpler, and closer to a real book. It loses for use case (i), because the operator explicitly wants to tunnel down references as tabs. The popover stays the <em>default</em>, with the tab one click away, so the book-like reader isn't forced into branching. Who pays: the book-first reader pays one extra click per tunnel, and the use-case-(i) reader pays nothing. The builder carries two code paths (popover and child tab), plus the text-only detection fallback for legacy documents.",
        rigor="Enumerate the link kinds in reader bodies before intercepting them: same-document anchor, other document in the graph, DOI, arXiv id, plain web URL, <code>mailto:</code>, and <code>javascript:</code> (strip it, it's a sanitiser failure). Each has an asserted behaviour. A same-document <code>#fn</code> anchor on another <code>paginate()</code> window is the tricky case, and it gets its own test.",
        diligence="Read <code>usePosition.ts</code> (the pagination and size-independence docblock), <code>paginate()</code>, <code>readingFocus.ts</code>, <code>ReadingCompanion</code>, <code>PersonalSpace</code> (<code>/readings</code>) and W3's <code>.prose-antiek</code> before building. Ingest strips Wikisource footnotes (reading-lane F1 in <code>ground/lane-a-reading-mothership.json</code>, not GAPS F1): read <code>acquisition/books/wikisource.py:93-114</code> and <code>paginate.ts:23-60</code>, so the UI's detection fallback matches what actually survives. Also read the PersonalSpace dwell query that feeds the Continue door.",
        defensibility="Record why Continue reads lane B's position record first and local position second, and why a citation open never writes position (it would clobber the operator's real place, R4). Put that in a comment at the position hook, citing R4 and MISS6. For the no-clobber rule, point to MS-05 M4 and its page-40 resume test rather than re-owning it. Record the Continue precedence in DECISIONS.md under D5."),
    upstream=[("MS-05", "openDocument, the ported Reader, the no-clobber position"), ("MS-04", "spawnChild and prefix+u"), ("MS-02 (W3 on main)", "the prose layer and states")],
    external=["Lane B: to-read flags (intent read, actor), durable position (a reading.position event), structured notes at ingest, a resolve-reference call, and a reading workstation kind (Q-A5).", "The ported rich Reader from MS-05."],
    out_of_scope=["Islands and asking an agent from the reader (MS-07).", "Ads layout changes. The attribution hooks must stay intact; ad design is not in scope.", "Rewriting ingest to keep footnotes (lane B)."],
    gates=[("Reader measurements", "story tests: chars per line, chrome % in focus mode, CLS", "60–72ch; under 10% chrome; CLS ≈ 0"),
           ("Keys", "vitest key-scope matrix", "pass"),
           ("Branches", "vitest: link click never leaves the workstation; prefix+u ×3 returns to the passage", "pass"),
           ("Themes", "tokens contrast test for day, night and paper", "AA"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="The Reading mothership is pushed and accepted. MS-07's islands mount on its reader.",
    harness=dict(pattern="inline", unit="None: the reader files are shared across milestones.",
                 why="Reader, keys and links all converge in modes/Reading and components/reader.",
                 lenses=["Does any path from inside a reader body leave the workstation, or move a book's saved position?",
                         "Are the Kindle claims measured (chars per line, chrome %, CLS, contrast), or only asserted?"],
                 lenses_short=["no escape from the workstation", "Kindle claims measured"]),
))

# ---------------------------------------------------------------- MS-07
SPRINTS.append(dict(
    id="MS-07", slug="islands-ask", wave=2, status="specced", budget="9 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Islands + ask",
    tagline="Highlight a passage and a subagent island hinges out beside it, bound to that passage. It keeps its conversation, shows its process and cost, and can be kept, promoted to a tab, or merged.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator: \"highlight a section that leads to an island emerging where I engage with an LLM "
        "deep research subagent, or just generally inquire a research agent and I can give it the context it needs without any highlight\".</p>"
        "<p>Grounding (<code>ground/lane-a-island-ask.json</code>, 15/15 checks held) found the pieces scattered:</p>"
        "<ul>"
        "<li>the shared <code>FloatMenu</code> (Note, Dialogue, Search, Deep-research) with an in-place multi-turn Dialogue (MISS4)</li>"
        "<li>a floating <code>ChaseThread</code> island in Research (MISS5)</li>"
        "<li>the reading-physics anchored-widgets kit, RegionStore and marginalia, BUILT_UNREACHABLE (IA-04)</li>"
        "<li>the <code>ContextPicker</code> in the AI sidecar</li>"
        "<li>TalkToBook</li>"
        "</ul>"
        "<p>What is missing:</p>"
        "<ul>"
        "<li>The island's lifetime is tied to the DOM selection (IA-01).</li>"
        "<li>Deep-research from a selection navigates away and, in the Reader, fails silently (F6).</li>"
        "<li>There is no model choice on the island (IA-09).</li>"
        "<li>There is no persistence or reopen (IA-05).</li>"
        "</ul>"
        "<p><strong>Contract (both lanes):</strong> an island IS a thread, created on its first question. Kept and promoted are "
        "presentation states. The anchor is a text-quote locator: passage_id stays the coarse key, extended with exact, prefix and suffix plus a position hint. "
        "<strong>Base:</strong> MS-06. <strong>Branch:</strong> <code>design/mothership-07-islands</code>.</p>"),
    position="Wave 2, after MS-06. The contract (THREAD-CONTRACT.md §2.3) must be signed by both lanes first. MS-08, MS-09 and MS-10 build on islands.",
    goal_line="One Island primitive, used identically in the Reader, Research and Writing. It is anchored, persistent and reopenable from a margin mark, shows cost before spend and process while it works, and never navigates away.",
    goal=("<p>From any selection, <code>prefix+a</code> (or the quiet Ask affordance) opens an island anchored to the span. The island hinges out of the "
          "anchor edge, the Popover hinge the PostHog grammar allows as its one perspective effect. It never covers the passage. It carries the "
          "model picker and an estimate, streams process steps and outcome, and can be kept (collapsing to a margin mark), promoted to a thread "
          "tab (a child in the MS-04 tree), or merged (MS-08). With nothing selected, the same island opens as an AskComposer, and you attach "
          "documents, notes or threads by hand.</p>"),
    milestones=[
        dict(title="IslandStore: lifetime independent of the DOM selection",
             desc="A Zustand <code>IslandStore</code> that snapshots <code>{anchor(text-quote locator), docId, workstationId, threadId?, state, presentation}</code> when the island opens. Closing the selection never closes the island.",
             criteria=["Tests: clearing the selection, scrolling and re-paginating keep the island and its anchor.", "The anchor survives re-projection of the HTML (the text-quote locator is re-resolved; test with a changed page window)."],
             files=["apps/reading/src/islands/IslandStore.ts (new)"]),
        dict(title="Island component: hinge physics, never covers text, 390 sheet",
             desc="Rendered through the reading-physics anchored-widgets facet (inline-end or right gutter). The Popover hinge (<code>perspective: 80rem</code>, <code>rotateX(±6deg)</code>, origin at the anchor edge) on the W5 motion tokens, with a plain appear under reduced motion. At sm the island is a full-height bottom sheet with a drag handle, Esc or swipe to close, a focus trap, and focus returned to the highlight (CR-05).",
             criteria=["A geometry test: the island's rect never intersects the anchored span's client rects at 1280, 1024 and 390.", "Reduced motion: no transform animation (test via matchMedia mock).", "Keyboard: the first control is focused on open, and Esc returns focus to the anchor (CR-03)."],
             files=["apps/reading/src/islands/Island.tsx (new, lazy)"]),
        dict(title="One primitive everywhere: Reader, Research, Writing",
             desc="Converge the FloatMenu Dialogue, the Research <code>ChaseThread</code> floating panel and the Write surface's span actions onto the Island. FloatMenu keeps its menu, and its \"Dialogue\" and \"Deep research\" items open the Island.",
             criteria=["A test per surface: selection → Ask → an island anchored to that span.", "The Reader's Deep-research no longer navigates to <code>/inv/:id</code>, and its failure is visible and retryable (F6 fixed)."],
             files=["apps/reading/src/modes/shared/FloatMenu/*", "apps/reading/src/modes/ResearchWorkstation/ChaseThread.tsx", "apps/reading/src/modes/Write/*"]),
        dict(title="Model picker + estimate before spend",
             desc="The existing <code>ModelUsagePicker</code> (#3400) in the island header, defaulting to the house route. Before the first question, the island shows the estimated cost (lane B's single-thread estimate; until then, the cascade spend-preview shape) and today's remaining cap (D4).",
             criteria=["No question can be sent without the estimate state having been shown (test).", "A <code>refused_capped</code> state renders the gate's reason and a one-step link to its setting, and an <code>estimate_unavailable</code> state shows a reason and never a figure (stories)."],
             files=["apps/reading/src/islands/IslandHeader.tsx (new)"]),
        dict(title="Streaming process + outcome, honest failure",
             desc="Island states: composing, estimating, running (process steps streaming, partial outcome), answered, failed (honest reason + Retry), refused_capped (before start) and stopped (mid-run). Process steps show the sources consulted, with their servability.",
             criteria=["A story for every state, light/dark, 1280/390.", "A test: a network failure mid-stream shows failed with Retry, and never a spinner forever or a silent close."],
             files=["apps/reading/src/islands/IslandStatus.tsx (new)"]),
        dict(title="Kept → margin mark; reopen from the passage",
             desc="Keeping collapses the island to a margin mark on the passage, through the marginalia augmentation. Reopening it rehydrates the thread's turns, process and outcome. The document's rail (MS-09) lists kept islands.",
             criteria=["A test: keep, reload and reopen from the mark show the same thread, with its turns and outcome."],
             files=["apps/reading/src/islands/*", "apps/reading/src/reading-physics/augmentations/*"]),
        dict(title="Promoted → a thread tab (a child in the branch tree)",
             desc="Promote opens the thread as a child tab of the current tab (<code>branch_origin.kind = island</code>). The island becomes its margin mark.",
             criteria=["A test: promote → a child tab with the right origin; <code>prefix+u</code> returns to the passage."],
             files=["apps/reading/src/islands/*", "apps/reading/src/workspace/tabTree.ts"]),
        dict(title="Ask without a highlight (AskComposer)",
             desc="<code>prefix+a</code> with nothing selected opens the same island, unanchored, as an AskComposer. Its context picker extends the existing <code>ContextPicker</code> (@doc, @insight) with threads (lane B adds a thread kind to <code>/compose-context</code>) and notes.",
             criteria=["A test: attach two documents and one thread → the request carries all three.", "Withheld or missing items show honestly (the ContextPicker's existing behaviour, preserved)."],
             files=["apps/reading/src/islands/AskComposer.tsx (new)", "apps/reading/src/components/ai/ContextPicker.tsx"]),
        dict(title="Bundle, stories, critic",
             desc="All island code is lazy.",
             criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."], files=[]),
    ],
    rigor=dict(
        honesty="Name three honesty risks. (1) Without lane B's thread continuation, a follow-up is a one-shot <code>/thought-partner</code> call with no history (<code>floatMenuActions.ts:209</code>). Say \"follow-up is stateless\", not \"Dialogue semantics\". (2) Until #3278 merges, Dialogue ignores <code>model_choice</code>, so the island's model picker must say so on Dialogue rather than pretend. (3) A local-only keep must not be labelled \"saved\".",
        fairness="Steelman keeping three separate surfaces (FloatMenu Dialogue, ChaseThread, Write span actions), each tuned to its mothership, with no convergence risk. It loses: three primitives means three lineages, three state models and three places for the next bug, which is the P0 clause's parallel-substitute failure. It has real affordances an anchored hinge could lose: ChaseThread's live ThinkingStream in a panel the user can drag anywhere, and Write's rewrite-in-place. Who pays: the Research operator's dragging habit, and this sprint's four-host FloatMenu refactor. Record which surface-specific behaviours were kept.",
        rigor="Test the geometry rule mechanically: the island never covers its anchor. Compute the anchor's <code>getClientRects()</code> and the island's rect at three widths and after scroll. \"Looks right\" is not a test. Split anchor handling in two. Re-pagination and re-projection must re-resolve the locator to the <em>same</em> exact/prefix/suffix text, tested with a changed page window. An edit or a re-ingest may lose it, and the island must then show an honest \"passage changed\" state rather than point at the wrong text. The geometry rule is no intersection at 1280 and 1024, and a bottom sheet at 390, where intersection is replaced by focus trap and return.",
        diligence="Before building, read <code>FloatMenu.tsx:418-513</code> (followUp state), <code>floatMenuActions.ts:209-230</code>, <code>ChaseThread.tsx:99-117</code>, the reading-physics anchored-widgets facet and RegionStore, <code>ContextPicker.tsx:28-88</code>, and the <code>ModelUsagePicker</code>. Also read <code>useFloatMenuSelection</code> (the IA-01 root), Write's <code>Outline.tsx:~605</code> span-action path, the Reading <code>spin-research</code> call site that navigates to <code>/inv/:id</code> (F6), the marginalia and chase-launcher augmentations (M6), and <code>workspace/tabTree.ts</code> (M7). The island must be assembled from these.",
        defensibility="Put the one-primitive decision, and the list of surfaces converged onto it, in a comment at the top of <code>Island.tsx</code>, with the ground ids (IA-01..IA-15, MISS4/5). The next person who wants a \"special island for X\" then sees why there is one. Also record the converged surfaces and the behaviours kept under \"Decisions made mid-flight\" in the handoff, and link the master spec's rejected-alternative row (\"a new island store separate from threads\")."),
    upstream=[("MS-06", "the reader it mounts on"), ("MS-05", "openDocument"), ("MS-04", "promotion to a child tab"), ("THREAD-CONTRACT.md signed", "island = thread, anchor locator")],
    external=["Lane B: thread continuation, the text-quote locator, stream endpoints, a single-thread estimate, a thread kind in <code>/compose-context</code>, and <code>model_choice</code> on spin-research (#3278 for Dialogue)."],
    out_of_scope=["Thread lists and the merge flow (MS-08).", "Companion rendering (MS-09).", "Flags and autonomous diligence from the island (MS-10)."],
    gates=[("Geometry", "vitest: the island never intersects its anchor at 1280/1024/390", "pass"),
           ("States", "Storybook: every island state, light/dark, 1280/390", "all rendered"),
           ("No navigate-away", "vitest: Deep-research from a selection in all three motherships", "stays in place; failure visible"),
           ("Keyboard + ARIA", "vitest focus-in and Esc-return tests", "pass"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="Islands exist everywhere and create threads, so MS-08 lists them and MS-09 renders what they found.",
    harness=dict(pattern="perspective-diverse-verify", unit="Build inline. Verify with distinct lenses.",
                 why="The build converges three surfaces into one primitive, so it is inline. The risks are geometry, lifetime and spend, which need diverse verification.",
                 lenses=["Anchor fidelity: after re-pagination, re-projection or an edit, does the island still point at the right text, or say honestly that it can't?",
                         "Spend honesty: can any question be sent without the model and estimate having been shown, or past today's cap?"],
                 lenses_short=["anchor fidelity after re-projection", "no spend without estimate/cap"]),
))

# ---------------------------------------------------------------- MS-08
SPRINTS.append(dict(
    id="MS-08", slug="threads-ux", wave=3, status="specced", budget="7 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Threads UX",
    tagline="Every subagent run is a thread you can find, reopen, ask again with its context, and merge with others while seeing where each claim came from.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator wants to \"ask that specific thread who holds that context to dig deeper\", and contexts "
        "\"merged manually or automatically\". Grounding (<code>ground/lane-a-threads-merge-fork-companion.json</code>):</p>"
        "<ul>"
        "<li>Per-document thread data exists but nothing serves it: <code>researches_for_passage</code>, chases parented to <code>read-&lt;doc&gt;</code>, and <code>read.book_answered</code> (C01, BUILT_UNREACHABLE).</li>"
        "<li>There is no per-workstation list (C02).</li>"
        "<li>Ask-this-thread is ABSENT (C03). DRW's Deepen follow-up is stored and never consumed.</li>"
        "<li>Manual merge is PARTIAL. ArtifactOutlineShelf's draft merge produces an output that can't be continued (C05).</li>"
        "<li>Automatic merge is ABSENT (C06).</li>"
        "<li>Process and outcome views exist for research threads, but not for Dialogue or TalkToBook (C07, C08).</li>"
        "</ul>"
        "<p><strong>Contract:</strong> row state derives from the event log's terminal reader. <code>merged_into</code> is investigation-level lineage. "
        "<strong>Base:</strong> MS-07. <strong>Branch:</strong> <code>design/mothership-08-threads</code>.</p>"),
    position="Wave 3. It needs MS-07 (threads come from islands) and lane B's thread lists, continuation and merge entity.",
    goal_line="Threads are listed where they were made (per document, per workstation), can be asked again with their held context, and can be merged with the provenance and conflicts made visible.",
    goal=("<p>The document's rail and its margin marks list its threads. The workstation's Threads tab and the sidebar list all of them with live state. "
          "Any row opens an \"ask this thread\" composer. Selecting two or more rows offers Merge: a preview tags every claim and source with its origin "
          "thread, conflicts are shown and never averaged, and accepting produces a merged thread with lineage. An automatic merge from lane B "
          "arrives as an inbox suggestion and is never applied silently.</p>"),
    milestones=[
        dict(title="Thread list per document (rail + margin marks)",
             desc="States: loading, empty (truthful), error, ready. Each row shows state, anchor, model, spend, last activity and source/claim counts, all from contract §2.4.",
             criteria=["Stories for every state; state derived only from the API (no client-side state column)."], files=["apps/reading/src/threads/DocThreads.tsx (new)"]),
        dict(title="Thread list per workstation (Threads tab + sidebar)",
             desc="The same rows, filterable by state and mothership, and virtualised for hundreds of threads.",
             criteria=["A fixture of 500 threads scrolls at 60 fps (measured, or NOT MEASURED with the reason)."], files=["apps/reading/src/threads/WorkstationThreads.tsx (new)"]),
        dict(title="Ask this thread",
             desc="A composer on any row continues that investigation with its held context, through lane B's continuation. It uses the same stream states as the island.",
             criteria=["A test: the request carries <code>thread_id</code>, and the new turns append to that thread (not a new thread)."], files=["apps/reading/src/threads/AskThread.tsx (new)"]),
        dict(title="Process view on every thread kind",
             desc="Steps, sources consulted (with servability) and a timeline, for research, Dialogue and TalkToBook threads alike.",
             criteria=["Stories for each thread kind."], files=["apps/reading/src/threads/ProcessView.tsx (new)"]),
        dict(title="Merge: select → preview → conflicts → accept",
             desc="Select two or more threads and choose Merge. The preview lists claims and sources with origin chips. Conflicts are shown side by side with a reason. Accepting produces a merged thread with <code>merged_from[]</code>, and the sources show <code>merged_into</code>.",
             criteria=["A test: conflicting claims are never collapsed into one.", "The lineage is visible on the sources and on the result (story)."], files=["apps/reading/src/threads/MergeFlow.tsx (new)"]),
        dict(title="Automatic merge suggestions via the inbox",
             desc="Lane B's merge suggestions appear as inbox items that open the same preview. No suggestion is applied without accept.",
             criteria=["A test: a suggestion never mutates a thread until accepted."], files=["apps/reading/src/shell/Inbox.tsx"]),
        dict(title="Bundle, stories, critic",
             desc="All lazy.", criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."], files=[]),
    ],
    rigor=dict(
        honesty="If lane B's merge entity isn't ready, the merge flow can preview but not accept. Ship it with Accept disabled <em>with a reason</em>: W2's <code>disabledReason</code> prop on LemonButton if it has landed, otherwise add the prop here. The flow then stops at contract §2.5's <code>previewing</code>/<code>conflicts_shown</code>, with no <code>merging</code>, and the stopping point is checked by a test. Never fake a merged thread client-side.",
        fairness="Steelman merging by concatenating two threads' outcomes into a note: cheap, and it works today. It fails the operator's ask. A concatenation can't be asked again, carries no lineage, and hides conflicts. Cheap merge is what ArtifactOutlineShelf already does (C05), and it was found insufficient. Who pays for the real merge: lane B builds the B2 merge engine and conflict detection (<code>{claim_a, claim_b, reason}</code>). Until it ships, the operator gets a merge that previews but cannot accept.",
        rigor="Conflict display is the correctness core. Build a fixture where two threads assert contradictory claims about the same source, and assert that the preview shows both, with origin chips and the conflict reason. Assert it never picks one. Also assert: a merge of three or more threads previews correctly; a merge <em>suggestion</em> leaves both sources' <code>merged_into</code> unset until accept; and an AskThread request carries <code>thread_id</code>, with its turns appended to that same investigation.",
        diligence="Read <code>MyResearch.tsx</code> (grouping and attention), ArtifactOutlineShelf's draft merge (<code>:128-151</code>), DRW steer (<code>ResearchPanel.tsx:71-92</code>) and the #3078 attention registry before building rows or merge. Before DocThreads, also read ReadingCompanion.tsx's saved-chases section and the backend <code>researches_for_passage</code> (C01). Before ProcessView, read the TalkToBook and Dialogue session stores (C07/C08).",
        defensibility="The rule that row state comes from the terminal reader, never a client field, goes in a comment on the shared row component (<code>apps/reading/src/threads/ThreadRow.tsx</code>, used by DocThreads and WorkstationThreads), citing the contract §2.4 agreement. Otherwise a future \"optimistic state\" shortcut will reintroduce the second state column."),
    upstream=[("MS-07", "islands create threads"), ("MS-03", "sidebar and inbox")],
    external=["Lane B: GET threads by document and by workstation, continuation, merge entity and suggestions."],
    out_of_scope=["Companion rendering and merge-into-document (MS-09).", "Flags (MS-10)."],
    gates=[("Conflicts", "vitest contradictory-claims fixture", "both shown, with origin and reason"),
           ("Continuation", "vitest: ask-this-thread appends to the same thread_id", "pass"),
           ("States", "stories for lists, composer, process and merge", "every state"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="Threads are listable, continuable and mergeable, so MS-09 can render and merge their findings into documents.",
    harness=dict(pattern="fan-out-and-synthesize", unit="Milestones 1–2 (lists), 3–4 (ask + process) and 5–6 (merge) are file-disjoint under apps/reading/src/threads/.",
                 why="Three disjoint component groups against one contract. Parallel builders then a synthesis pass beat serial.",
                 lenses=["Can any UI path show a thread state that the terminal reader would not report?",
                         "Can a merge hide a conflict or lose a source's lineage?"],
                 lenses_short=["state only from terminal reader", "merge never hides conflict/lineage"]),
))

# ---------------------------------------------------------------- MS-09
SPRINTS.append(dict(
    id="MS-09", slug="companion-merge-fork", wave=3, status="specced", budget="7 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Companion + merge-into-document + fork",
    tagline="What the subagents found becomes a readable companion per project and per document. Any finding can be merged into your writing as a fork you review hunk by hunk.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator wants outcomes \"recorded as a human facing companion document to each project and each "
        "evidence document, while also maintaining an agent facing more rich version\", and wants to merge insights into a document to \"create a forked version\".</p>"
        "<p>D3 rules: a Companion <em>tab</em> per workstation, plus a slim companion <em>rail</em> beside each evidence document. Grounding found:</p>"
        "<ul>"
        "<li>AutoNotebook is a per-investigation companion (C09 PARTIAL).</li>"
        "<li>ReadingCompanion is a per-document one (C10 PARTIAL).</li>"
        "<li>Merge-into-document is PARTIAL (C12).</li>"
        "<li>A fork-with-lineage primitive, <code>create_document_version</code>, exists with no production caller (C13, MISS6).</li>"
        "<li>There is no diff/accept UI at all (C14 ABSENT).</li>"
        "</ul>"
        "<p><strong>Lane B guardrails:</strong> the companion derives from research-artifact and html_projection projections, never a parallel document model. "
        "Fork reuses the HTML-projection fork lineage and Write documents. "
        "<strong>Base:</strong> MS-08. <strong>Branch:</strong> <code>design/mothership-09-companion</code>.</p>"),
    position="Wave 3, after MS-08. It needs lane B's derived companion, merge-proposal endpoint and fork repository.",
    goal_line="Every workstation has a Companion tab and every evidence document a companion rail, both rendering lane B's derived companion. Any entry can be merged into a writing document as a fork, reviewed per hunk.",
    goal=("<p>The companion leads with outcome (claims, open questions, key insights) and keeps process one click deep. Margin marks and rail "
          "entries point at each other. \"Merge into…\" picks a Write document in the workstation, drafts the insertion with provenance, and "
          "opens DiffReview. Accepting creates a fork with lineage; the original is never touched. The agent-facing evidence base is lane B's; "
          "lane A renders only a link to it.</p>"),
    milestones=[
        dict(title="Companion tab (per workstation)",
             desc="Renders the derived companion: sections for claims, open questions and key insights. Each entry shows confidence, sources and its threads. States: loading, empty (truthful), error, stale (newer results exist: Refresh).",
             criteria=["Stories for every state.", "Every entry links to its thread's process view (MS-08)."], files=["apps/reading/src/companion/CompanionTab.tsx (new, lazy)"]),
        dict(title="Companion rail (per evidence document, D3)",
             desc="A slim rail beside the reader: the same companion filtered to this document, with margin marks ↔ rail entries both ways. At 390 px it is a sheet (CR-07). <code>prefix+r</code> toggles it.",
             criteria=["A geometry test: the rail never narrows the reading column below 60ch at 1280.", "Keyboard + focus return tests."], files=["apps/reading/src/companion/CompanionRail.tsx (new, lazy)"]),
        dict(title="\"How I got here\" from the branch record",
             desc="For any entry, show the path of branches (lane B's provenance record) that led to it. It reads the branch record, not the tab tree (contract §2.2).",
             criteria=["A test: pruning tabs does not change the \"how I got here\" path."], files=["apps/reading/src/companion/Provenance.tsx (new)"]),
        dict(title="Merge into… (choose target, draft with provenance)",
             desc="From a companion entry or a thread outcome, choose a Write document in the workstation. Lane B drafts the proposed hunks (anchor, insert_html, source_refs).",
             criteria=["States: choose, drafting, failed, ready (stories)."], files=["apps/reading/src/companion/MergeInto.tsx (new)"]),
        dict(title="DiffReview: per-hunk accept or discard",
             desc="A block-level diff between the parent version and the proposal. Each hunk is accepted or discarded, and shows its source (AI or operator) with its sources. Keyboard: j/k between hunks, a to accept, d to discard, both in the keymap table.",
             criteria=["Tests: a partial accept creates a fork with exactly the accepted hunks; discard-all creates nothing.", "Screen-reader labels on every hunk action."], files=["apps/reading/src/companion/DiffReview.tsx (new, lazy)"]),
        dict(title="Fork chip + lineage",
             desc="The Write document header shows its fork lineage (parent version and the merged source threads). You can open the parent, or compare against it.",
             criteria=["A test: the original document is byte-identical after a merge."], files=["apps/reading/src/modes/Write/*"]),
        dict(title="Bundle, stories, critic",
             desc="All lazy.", criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."], files=[]),
    ],
    rigor=dict(
        honesty="A companion built from partial data must say so (\"3 of 7 threads summarised\"), never present itself as complete. That needs coverage fields, which is a lane B ask: add <code>summarised_thread_count</code> and <code>total_thread_count</code> to contract §2.7, and render the partial state from them, with a story next to loading, empty, error and stale. If the endpoint returns stale data, show the stale state rather than hiding it.",
        fairness="Steelman rendering the companion from AutoNotebook directly, since it already exists per investigation. It loses because AutoNotebook is per investigation, not per project or per document, and D3 needs both scopes from one derivation (lane B B3). AutoNotebook's section model (synthesis, insights, questions) is reused as the rendering shape. Who pays: lane B must ship the B3 derived-companion endpoint, and until then the tab and rail sit in empty or stale states. ReadingCompanion's per-document marginalia (C10) is not the rail's source, because it holds only that reader's notes, not every thread's findings.",
        rigor="The original-is-untouched guarantee is the critical invariant. Assert byte identity of the parent version before and after every merge path: accept all, accept some, discard all, and a failed merge. A partial accept's fork must contain exactly the accepted hunks, compared against <code>proposed_hunks[]</code> by anchor. Discard-all must produce no <code>fork_id</code>.",
        diligence="There is <em>no</em> Write version model on main (grounding). Fork versions come from <code>substrate/research_bridge/versioning.py</code> (<code>create_document_version</code>, no production caller yet) or the SDAM derived-asset revision tables. Read those, plus <code>source_merge.py</code> (and Sweep v2's path-confinement fix <code>9052cf933</code>, which changed its preflight), <code>artifact_routes.py</code>, <code>deriveAutoNotebook.ts</code>, <code>ReadingCompanion.tsx</code> and the HTML-projection lineage before rendering or merging.",
        defensibility="Record in DiffReview's header comment why merges create forks and never edit in place, quoting the operator's goal line (\"merge their data into the document and create a forked version\"), with DESIGN-MODEL.md §5 and THREAD-CONTRACT.md §2.6. Also record why per-hunk rather than whole-document accept: the operator's own writing stays his."),
    upstream=[("MS-08", "threads and process views"), ("MS-05", "the reader the rail sits beside")],
    external=["Lane B: the companion document (§1.12, after the rights branches), the derived-asset revision repository with diff and per-hunk accept/reject (§1.11), and the branch record (§1.3)."],
    out_of_scope=["Editing the agent-facing evidence base (lane B).", "Flags (MS-10)."],
    gates=[("Original untouched", "vitest byte-identity across every merge path", "pass"),
           ("Rail geometry", "the column stays ≥ 60ch with the rail open at 1280", "pass"),
           ("States", "stories: companion tab, rail, merge-into, DiffReview", "every state"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="Findings are readable and mergeable, so MS-10's autonomous results have somewhere to land.",
    harness=dict(pattern="fan-out-and-synthesize", unit="Companion (1–3) vs merge and fork (4–6) are file-disjoint.",
                 why="Two disjoint groups against the contract.",
                 lenses=["Can any merge path modify the original document or drop a hunk's provenance?",
                         "Does the rail ever squeeze the reading column below the measure, or hide that the companion is partial or stale?"],
                 lenses_short=["original untouched; provenance kept", "rail never breaks measure; partial shown"]),
))

# ---------------------------------------------------------------- MS-10
SPRINTS.append(dict(
    id="MS-10", slug="flags-consent-autonomy", wave=3, status="specced", budget="7 milestones",
    owner="Antiek Nudge v2 (lane A)",
    title="Flags, consent, autonomy, inbox",
    tagline="Flag a passage, claim, question or insight to read later or to have it diligenced. Nothing runs without your consent, and nothing spends past your daily cap.",
    context=(
        "<p><strong>What this sprint is about.</strong> The operator: \"flagged concepts, open questions, and key insights can be autonomously diligenced\". "
        "D4 rules: opt-in per flag, a user-set daily cap reserved before spend, results into the thread and companion, and an attention inbox. "
        "D5 adds <code>intent: read</code> flags set by the user <em>or an agent</em> (the Reading mothership's To-read door).</p>"
        "<p>Grounding (<code>ground/lane-a-autonomy-and-craft-baseline.json</code>):</p>"
        "<ul>"
        "<li>Flagging a concept is ABSENT (AD-01), an open question PARTIAL (AD-02), a key insight weak (AD-03).</li>"
        "<li>The continuous-research daemon is BUILT_UNREACHABLE, because its SpawnFn is a stub (AD-04).</li>"
        "<li><code>chase_mode</code> is BUILT_UNREACHABLE, not on the start request (AD-05).</li>"
        "<li>Human-gated chase of suggested gaps works (AD-06).</li>"
        "<li>There are no autonomy settings (AD-09), but the cascade spend-preview and owner-bound approval exist to follow.</li>"
        "</ul>"
        "<p>A honesty defect sits next door (MISS9): the Notebook question card promises \"will surface as a parked question\" and does not. "
        "<strong>Base:</strong> MS-08. <strong>Branch:</strong> <code>design/mothership-10-flags</code>.</p>"),
    position="Wave 3. It needs MS-03 (the inbox), MS-08 (threads) and lane B's flag entity, consent event, cap ledger, daemon SpawnFn and <code>chase_mode</code>.",
    goal_line="Flags exist everywhere a user looks at knowledge. Diligence runs only after per-flag consent that shows model, estimate and remaining cap. Results land in threads, the companion and the inbox.",
    goal=("<p>A flag action sits on the island, the FloatMenu, companion entries, thread rows and open-question rows. The consent sheet shows the model, the "
          "estimate and today's remaining cap, with Accept or Decline. Accepted flags queue as threads and show their state. At the cap they stop "
          "as <code>refused_capped</code>, with a one-step raise. The Autonomy settings panel holds the daily cap and the per-run ceiling. \"Keep digging\" "
          "on a thread exposes <code>chase_mode</code> depth, duration and budget.</p>"),
    milestones=[
        dict(title="Flag actions everywhere (read | diligence)",
             desc="One flag action with an intent choice, on the island, FloatMenu, companion entries, thread rows and open-question rows. Agent-set flags are labelled as agent-set.",
             criteria=["A test per surface: the flag carries the right target and intent.", "Agent-set and user-set flags differ by label and icon, not colour alone."], files=["apps/reading/src/flags/* (new)"]),
        dict(title="Consent sheet",
             desc="For a diligence flag: model (ModelUsagePicker), estimate, today's remaining cap, and Accept or Decline. Nothing is queued without Accept (D4).",
             criteria=["A test: no run is queued without an explicit accept.", "Capped state: Accept is disabled with a reason, plus a \"raise today's cap\" link."], files=["apps/reading/src/flags/ConsentSheet.tsx (new, lazy)"]),
        dict(title="Autonomy settings (daily cap, per-run ceiling)",
             desc="Settings → Autonomy. The daily cap and per-run ceiling are written to lane B's cap ledger. Show spent today and remaining as numbers, never estimated as zero when unknown.",
             criteria=["States: loading, error, ready.", "An unknown spend shows \"—\", never 0 (the W7 rule)."], files=["apps/reading/src/modes/Settings/AutonomyPanel.tsx (new)"]),
        dict(title="Flag queue + inbox items",
             desc="A Flags tab per workstation listing flags by state (flagged, consent_pending, queued, running, done, failed, stopped, refused with its reason, declined). Inbox items for consent needed, done, refused_capped and merge suggestions.",
             criteria=["Stories for every state, light/dark, 1280/390."], files=["apps/reading/src/flags/FlagQueue.tsx (new, lazy)", "apps/reading/src/shell/Inbox.tsx"]),
        dict(title="\"Keep digging\" (chase_mode)",
             desc="On a thread: depth N or hours H, with a $ ceiling, through lane B's <code>chase_mode</code> on the start request. The same consent sheet.",
             criteria=["A test: the request carries <code>chase_mode</code>, <code>chase_value</code> and <code>chase_budget_usd</code> only after consent."], files=["apps/reading/src/threads/KeepDigging.tsx (new)"]),
        dict(title="Fix the Notebook question-card honesty defect",
             desc="The card says \"will surface as a parked question\" but nothing parks it (MISS9). Either wire it to the flag entity (<code>intent: diligence</code>, consent-pending) or change the copy to what actually happens.",
             criteria=["A test: the card's promise matches its effect."], files=["apps/reading/src/modes/Notebook/NotebookCanvas.tsx"]),
        dict(title="Bundle, stories, critic",
             desc="All lazy.", criteria=["<code>build:check</code> within budget.", "Codex critic ACCEPT."], files=[]),
    ],
    rigor=dict(
        honesty="Autonomy spends the operator's money unattended. Every figure the UI shows (estimate, spent today, remaining) must come from lane B's ledger. If it is unavailable, show \"—\" and block Accept with a reason. Never show a guessed cap.",
        fairness="Steelman auto-diligencing every flag within the cap: less friction, and the operator could raise the cap himself. He ruled opt-in per flag (D4), and the cost of the extra click falls on him. Make that click one keystroke from the flag (Enter accepts the defaults) rather than removing it.",
        rigor="Enumerate the spend paths (consent → queue → run → follow-up → chase) and assert for each that the cap is reserved before spend (lane B) and that the UI blocks when the reservation fails. One test per path. Name two further cases as tests: refused_capped (Accept disabled with a reason, plus \"raise today's cap\") and unknown ledger (\"—\" blocks Accept). Also assert that <code>chase_mode</code>, <code>chase_value</code> and <code>chase_budget_usd</code> are absent from the start request before consent.",
        diligence="Before building consent, read <code>interfaces/research/api/cascade_routes.py:810,1203-1235</code> (spend-preview and owner-bound approval), <code>CascadeProposal.tsx</code> (the existing approval UI), <code>SuggestedResearch</code>'s states (CR-06), <code>orchestration/loop_one/orchestrator.py:2270-2382</code> (<code>chase_mode</code>), <code>NotebookCanvas.tsx:422-430</code> (the \"will surface as a parked question\" copy, MISS9) and <code>ground/lane-a-autonomy-and-craft-baseline.json</code>.",
        defensibility="The consent sheet's copy and its no-accept-no-run rule cite D4 in a comment. The Autonomy panel records the operator's cap as he set it, plus an audit line (from lane B) of each change, so \"why did it spend that?\" is answerable."),
    upstream=[("MS-08", "threads and the inbox wiring"), ("MS-03", "the inbox surface"), ("MS-07", "the island flag action")],
    external=["Lane B: flag entity, consent event, reserve-before-spend cap ledger, daemon SpawnFn, <code>chase_mode</code> on the start request, and inbox items."],
    out_of_scope=["Standing topics, schedules and re-ingestion (the never-sleeping-agent spec). Autonomy here is flag-driven only.", "Autoresearch tuning (not user diligence)."],
    gates=[("Consent", "vitest: no run without accept, on every spend path", "pass"),
           ("Cap", "vitest: a reservation failure blocks with a reason", "pass"),
           ("No invented numbers", "vitest: unknown spend shows —", "pass"),
           ("States", "stories: flags, consent, queue, autonomy", "every state"),
           ("Bundle", "npm run build:check", "within budget"),
           ("Critic", "codex exec … < /dev/null", "ACCEPT")],
    next_when="Flags and autonomy exist, so MS-11 re-scores the whole system.",
    harness=dict(pattern="inline", unit="None: consent is one owning flow across surfaces.",
                 why="The consent rule must be one implementation, applied to every surface.",
                 lenses=["Is there any path where money is spent without per-flag consent, or past the cap?"],
                 lenses_short=["no spend without consent or past cap"]),
))

# ---------------------------------------------------------------- MS-11
SPRINTS.append(dict(
    id="MS-11", slug="proof-rubric-states", wave=3, status="specced", budget="6 milestones",
    owner="Antiek Nudge v2 (lane A) + an independent scorer",
    title="Proof: rubric re-score + state matrices",
    tagline="Prove it the way the audit measured it: an independent rubric re-score at or above 87.5% with no veto, every state in both themes at two widths, and a rendered walkthrough at the operator's real scale.",
    context=(
        "<p><strong>What this sprint is about.</strong> The 2026-09-23 audit scored the UI 24/48 (50%) with two vetoes failed, against a floor of 42/48 "
        "(<code>/Users/slimydog/.claude/jobs/236c36bd/tmp/design-audit/SCORE-BASELINE-full.md</code>; rubric: the operator's frontend-craft skill, "
        "<code>~/.claude/skills/frontend-craft/references/CRAFT-RUBRIC.md</code>). W7 closed one veto on five pages. This sprint re-scores the "
        "whole mothership independently, by a scorer who did not build it, and records what the operator's day looks like at his herdr scale "
        "(20 workstations, 252 tabs, one 174-tab tree).</p>"
        "<p><strong>Base:</strong> main after MS-01..MS-10 land.</p>"),
    position="The last sprint of wave 3. It is the done-bar for lane A.",
    goal_line="An independent scorer re-scores the rubric at ≥ 42/48 with no critical-failure veto, and every new surface has its complete state matrix in stories on the dark lostpixel axis.",
    goal=("<p>The walkthrough renders:</p>"
          "<ol>"
          "<li>open three workstations</li>"
          "<li>hop by prefix</li>"
          "<li>read a book</li>"
          "<li>open a footnote as a tab, then three levels of references</li>"
          "<li>raise an island on a passage</li>"
          "<li>keep it</li>"
          "<li>ask an older thread</li>"
          "<li>merge two threads</li>"
          "<li>merge an insight into a draft and review the fork</li>"
          "<li>flag an open question for diligence with consent</li>"
          "<li>see it land in the inbox</li>"
          "</ol>"
          "<p>It runs in light and dark at 1280 and 390, with screenshots saved.</p>"),
    milestones=[
        dict(title="State-matrix stories for every new surface",
             desc="Every surface from MS-01..MS-10, in every state, light/dark, at 1280 and 390, on W6's dark lostpixel axis.",
             criteria=["A test lists every new component and fails if one has no story for any designed state."], files=["apps/reading/src/**/*.stories.tsx"]),
        dict(title="Herdr-scale fixture + rendered walkthrough",
             desc="A seeded fixture (20 workstations, 252 tabs, a 174-tab tree, depth > 12) and the goal's walkthrough as a Playwright script against a local build, saving screenshots.",
             criteria=["The screenshots are saved and listed. Any step that could not run is marked NOT RUN with the reason."], files=["apps/reading/e2e/mothership-walkthrough.spec.ts (new)"]),
        dict(title="Independent rubric re-score",
             desc="A scorer who did not build these sprints (codex gpt-6-sol, or a fresh Opus session given only the rubric and the rendered evidence) scores all 12 dimensions with evidence per score, and checks every veto.",
             criteria=["≥ 42/48 and no veto. Otherwise the gaps become a named follow-up list, and the result is reported as it is."], files=[".lane/RESCORE.md"]),
        dict(title="Accessibility pass in both themes",
             desc="axe over every story in both themes (W1's harness), and a keyboard-only walkthrough of the goal flow.",
             criteria=["0 serious or critical axe violations on new surfaces; the keyboard-only walkthrough completes."], files=[".lane/a11y/*"]),
        dict(title="Bundle and performance record",
             desc="Entry chunk headroom; switcher p95 on the fixture; tree panel fps at 174 nodes.",
             criteria=["Numbers are recorded against the gates set in MS-03 and MS-04."], files=[".lane/perf.md"]),
        dict(title="Operator-facing summary",
             desc="One HTML page, per frontend-craft §6: what changed, the walkthrough screenshots, the score, and what is left.",
             criteria=["The page is self-contained and cites the evidence files."], files=["/Users/slimydog/Antiek/specs/antiek-mothership/RESULT.html (new)"]),
    ],
    rigor=dict(
        honesty="Lane A is built by Claude sessions, so a fresh Opus session is <em>same lineage</em>. It may produce a first score, but that score is provisional until codex gpt-6-sol (or another non-Claude scorer) confirms it. Milestone 3 means this. The score is judged against ≥ 42/48 with zero vetoes, beside the 24/48 two-veto baseline. Report the provisional and the confirmed score separately.",
        fairness="Steelman scoring only the new surfaces, since that is where the work went. It loses: the operator uses the whole app, and the audit's baseline was whole-app, so a partial re-score is not comparable. Name who pays: the whole-app score can stay under 42/48 because of defects lane A did not introduce (for example the MascotStation-obscures-content veto in SCORE-BASELINE-full.md). The separate new-surface sub-score is how that cost is made visible rather than hidden.",
        rigor="Six mechanical checks. (a) <code>.lane/RESCORE.md</code> sums all 12 dimensions, and every veto row has an explicit PASS or FAIL with evidence. (b) Each score cites a screenshot from the <code>e2e/mothership-walkthrough.spec.ts</code> run or a story id; a score without an evidence path is capped at 1, per <code>CRAFT-RUBRIC.md:3</code>. (c) The story-coverage test fails when any MS-01..MS-10 component lacks a designed state in light or dark at 1280 or 390. (d) axe reports 0 serious or critical violations on new surfaces. (e) A walkthrough step that could not run is written NOT RUN with its reason, never omitted. (f) The fixture really has 20 workstations, 252 tabs, a 174-tab tree and depth > 12, asserted by the fixture's own test.",
        diligence="Before scoring, read <code>/Users/slimydog/.claude/jobs/236c36bd/tmp/design-audit/SCORE-BASELINE-full.md</code>: the dimension table from :38 and the veto table from :56. Re-check each named finding, including <code>Library/index.tsx:566-571</code> (the invented zero W7 fixed) and <code>MascotStation.tsx:103-104</code> / <code>zIndex.ts:120</code> (obscures content). Also read <code>~/.claude/skills/frontend-craft/references/CRAFT-RUBRIC.md</code> (the evidence rule at :3, the vetoes in §3, and the \"Not proved\" requirement in §5), plus MS-03's switcher-p95 and MS-04's tree-fps gates, before writing <code>.lane/perf.md</code>.",
        defensibility="<code>.lane/RESCORE.md</code> is the record. Per dimension it holds the baseline and new score, the evidence, and the veto results. It also records the scorer's model and lineage, and ends with a \"Not proved\" section (CRAFT-RUBRIC §5). <code>RESULT.html</code> cites it, and the next audit starts from it rather than from SCORE-BASELINE-full.md."),
    upstream=[("MS-01..MS-10", "everything under test")],
    external=["Playwright with Chrome for the walkthrough (NOT RUN if it cannot launch).", "An independent scorer."],
    out_of_scope=["Fixing what the re-score finds. Findings become follow-up sprints; this sprint reports."],
    gates=[("Rubric", "the independent re-score", "≥ 42/48, no veto (or reported as it is)"),
           ("Stories", "the state-matrix completeness test", "pass"),
           ("A11y", "axe over stories in both themes", "0 serious or critical on new surfaces"),
           ("Walkthrough", "Playwright mothership-walkthrough", "every step RUN or marked NOT RUN with reason")],
    next_when="Lane A is done when this sprint's gates pass or are honestly reported.",
    harness=dict(pattern="perspective-diverse-verify", unit="Scoring dimensions can be scored independently.",
                 why="Independence is the whole point of a re-score.",
                 lenses=["Craft (physics, restraint, states) against the frontend-craft rubric.",
                         "Honesty (no invented facts, no hidden spend) against the two vetoes."],
                 lenses_short=["craft vs rubric", "honesty vetoes"]),
))

CONTRACT = {
  "MS-03": [
    "The data noun is <strong>project</strong>; \"workstation\" is the UI noun. The registry is <code>/projects</code> (GET list, POST, PATCH /{id}, members, GET /{id}), backed by the extended <code>write_folders</code> store with <code>kind: project|reading</code> (§1.5). Your adapter targets these routes.",
    "Aggregates are <code>thread_counts {running, needs_you, done_unseen}</code> and <code>spend_today {cents, currency} | null</code> (§1.5). A null renders \"—\" with its reason, never <code>$0.00</code> (Part 2 nullable rule).",
    "Live state is a nudge on <code>WS /ws/events</code> (§1.7); catch-up after a reconnect is the durable <code>GET /inbox?after=&lt;cursor&gt;</code>, never the socket alone (§1.13). The inbox kinds are <code>thread_done, thread_needs_you, flag_consent, refused_capped, merge_suggestion</code>.",
  ],
  "MS-04": [
    "Tab persistence is <code>GET /projects/{id}/tabs/{mothership}</code> → <code>{tree, active_tab_id, version}</code> and <code>PUT</code> with <code>{tree, active_tab_id, expected_version}</code> (§1.6). Write debounced whole-tree snapshots. On <code>409 {current}</code>, replay pending local operations on <code>current</code> and PUT again; an operation on a tab another device closed is dropped with one quiet toast (Part 2 §2.2).",
    "<code>public_number</code> comes from <code>POST /projects/{id}/tabs/{mothership}/allocate</code>: workstation-wide, never reused even after close. Until it returns, the tab is in <code>numbering</code> (open, reachable by n/p/w, not by digit). Never invent a number locally.",
    "<code>hier_number</code> is computed client-side as <code>&lt;parent&gt;.&lt;next unused child index&gt;</code> counting retired numbers, validated on the PUT and final once accepted; on a 409, recompute pending spawns before acceptance so every local spawn survives (R3-5). Closed and pruned numbers go to <code>retired_numbers</code> keyed by <code>tab_id</code>; restoring the same <code>tab_id</code> reclaims them, a different one never may (R3-1). Hold a close locally through its 10 s undo window so other devices never see an undone close.",
    "A branch is a durable dependency, not proof the child ran (§1.3). A thread tab can read <code>no_record</code> (a crash-orphan or a lost log: the branch stays live and fails closed), <code>abandoned</code> (only <code>capacity_refused</code> or an operator reconciliation) or <code>spawn_refused</code> (<code>422 parent_investigation_not_found</code> or <code>409 reservation_parent_mismatch</code>); each is designed (Part 2 §2.2). Tabs never point at reserved-only ids. A pending spawn whose parent closed remotely re-attaches to the nearest surviving ancestor (or root) with a fresh number; a replayed prune never closes tabs this device hasn't seen (lift them). Restore from history reads the server's <code>retired[]</code> descriptors. <code>branch_origin.kind</code> \"island\" is <code>selection</code> in the backend.",
  ],
  "MS-05": [
    "Non-book documents (F8) are served to the reader in lane B's W1 (§1.18). Until then, the honest \"not stored yet\" state stands.",
    "Reading position is <code>reading.position</code> on <code>read-&lt;documentId&gt;</code>, read by <code>GET /documents/{id}/position</code> and written by <code>PUT /documents/{id}/position {anchor, percent}</code> (§1.14). The log is authoritative, so write sparingly: after 10 s of settled scrolling, on leaving the document (<code>pagehide</code> with <code>keepalive</code>), never when unchanged. Opening at a citation must never write it.",
  ],
  "MS-06": [
    "The Continue door is <code>GET /reading/continue</code>, and per-document position is <code>GET /documents/{id}/position</code> (§1.14).",
    "The To-read door is <code>GET /flags?intent=read</code>. <code>actor {kind, id}</code> is server-derived; the label is \"You\" or the agent's role name (§1.13, Part 2 §2.8).",
    "A standalone book is a <code>kind: reading</code> project with <code>primary_document_id</code>, promoted in place by \"Add to project…\" (§1.5).",
    "Reading threads read <code>idle</code>, never \"working\" (§1.2).",
  ],
  "MS-07": [
    "The anchor is §1.4's <code>BranchAnchor</code> (<code>source_locator</code> TextLocator, <code>quote</code>, <code>prefix</code>, <code>suffix</code>, <code>region_id?</code>, <code>page_index?</code>). When the text hash no longer matches, <code>POST /documents/{id}/anchors/remap</code> returns <code>resolved | ambiguous | unresolved</code> with scored candidates; the operator's pick writes <code>anchor.resolved</code> so it is asked once (§1.4, Part 2 §2.3). <code>passage_research</code> is page-granular today (§1.1.1).",
    "An island's thread branches from <code>read-&lt;documentId&gt;</code> with origin <code>selection</code> (§1.3). Do <strong>not</strong> ship the attach-context UI until §1.9's <code>context_items</code> lands: unknown fields are silently dropped today.",
    "The estimate is <code>POST /investigations/estimate</code> → <code>{cents, basis, status: ok|unavailable, reason?}</code> (§1.9). <code>unavailable</code> shows its reason and never a figure; launch needs an explicit \"Cost unknown\" confirmation. An ACU refusal is <code>refused_capped</code> before start; a mid-run halt is <code>stopped</code>.",
    "\"Island\" is a lane A presentation word only. Component names may use it; routes, events and payloads never do (§1.0).",
    "Follow-up: tier 0 is <code>POST /investigations/{id}/ask</code> (a conversation turn). Tier 1 is <code>continue_from_parent</code> (a new research run, with its own estimate). They are two distinct actions (§1.8).",
  ],
  "MS-08": [
    "Row states are <code>queued, running, needs_you, done, failed, stopped, idle</code> (reading threads) and <code>merged_into</code>; <code>done</code> carries an unseen marker from <code>thread_seen</code>. Opening a thread sends <code>POST /investigations/{id}/seen {through_event_id}</code>, only ever forward (§1.5). There is no <code>capped</code> row state (§1.1.4).",
    "Lists come from <code>GET /investigations</code> with <code>project_id</code>, <code>document_id</code>, <code>kind</code>, <code>state</code> and <code>parent_thread_id</code> filters (§1.2). <code>claim_count</code>, <code>source_count</code> and <code>spend_cents</code> are nullable and render \"—\" with a reason. The process view is a projection of <code>GET /trajectory/{id}</code>.",
    "Merge preview is <code>POST /threads/merge/preview</code> → <code>{preview_digest, items[], conflicts[]}</code>. Commit is <code>POST /threads/merge {thread_ids[], preview_digest, question, idempotency_key}</code>: <code>409 preview_stale</code> (the digest covers gated text, pointers and rights) re-previews and keeps the question; <code>503</code> means nothing has run, and Retry with the same key resumes from <code>thread.merge_started</code>. Show <code>merged</code> only when the start event is confirmed; member rows read <code>merge_pending</code> / <code>merge_failed</code> until then (§1.10, Part 2 §2.4–2.5). <code>409 idempotency_conflict</code> is a lane-A bug. Every item is a <code>GatedText</code>: render Part 2 §2.10 by <code>gate</code>, never by empty text.",
  ],
  "MS-09": [
    "A document fork is a <strong>derived-asset revision</strong> on <code>write:&lt;deliverable_id&gt;</code>, the one mapping (§1.11). The flow is merge-drafts → per-hunk review (<code>review_id</code>) → <code>POST …/revisions {review_id, acknowledgement: \"new_revision\", idempotency_key}</code> (CAS) → lineage. <code>409 revision_moved</code> is <code>base_moved</code>: re-draft, and carry decisions only for byte-identical hunks. Revision 1 is written on first use, so the lineage always has an original. Each hunk's insertion is a <code>GatedText</code>: a cite-only hunk inserts a citation only, a withheld hunk can only be rejected (§1.11, Part 2 §2.6).",
    "Legacy commit fields answer 422, and that is a lane-A bug. Source merge is retired, so never offer it. Write blocks are not a merge target.",
    "The companion document returns <code>{entries[], content_hash, covered: {thread_id: through_event_id}, summarised_thread_count, total_thread_count, state}</code> (§1.12). Design <code>stale</code>, <code>refreshing</code> (<code>POST …/refresh</code> writes a receipt), <code>partial</code> (\"n of m threads summarised\") and <code>unavailable_until_rights</code>. Entries link their process by <code>process_ref</code>.",
  ],
  "MS-10": [
    "A flag is a question-family event: <code>question.identified</code> plus <code>intent</code>, a server-derived <code>actor</code>, <code>target</code> and <code>reason</code>; <code>flag_id</code> is the <code>question_id</code>. The lifecycle is <code>question.diligence_consented / _declined / _launched / _refused</code> (§1.13). Lists come from <code>GET /flags?intent=&amp;project_id=</code>.",
    "Routes: <code>POST /flags</code>, <code>POST /flags/{id}/consent</code> (bound to target + context version), <code>POST /flags/{id}/decline</code>, <code>POST /flags/{id}/launch {consent_id}</code>. Accept is consent then launch behind one press; a failed launch retries with the same <code>consent_id</code>. <code>409 consent_stale</code> re-asks with a fresh estimate. With an <code>unavailable</code> estimate, consent is not offered (R3-2). A reserved question reads <code>reserved</code>.",
    "Admission holds nothing: a launch starts if the run's remaining (cap − spent − held) covers X = estimate × 1.5 or the tier max. The consent copy is exactly \"Starts if $X of today's cap is free; it pauses if the cap runs out\" — never \"held\". Only dispatches hold (<code>reserve_dispatch</code>). <code>daily_cap_cents</code>, <code>spent_today_cents | null</code> and <code>held_today_cents | null</code> are on <code>GET /settings/budget</code>; raising the cap is <code>PUT /settings/budget/daily-cap</code>. Refusal reasons: <code>refused_capped</code>, <code>unavailable</code>, <code>failed</code>; a mid-run pause reads <code>stopped</code> with <code>cap_reached</code> or <code>cap_overshoot</code> (R5-3, R5-4).",
    "<code>chase_mode</code> joins <code>InvestigationStartRequest</code>, and the daemon's <code>SpawnFn</code> routes through the API as a branch-writing launch (§1.13).",
  ],
}
for _sp in SPRINTS:
    if _sp["id"] in CONTRACT:
        _sp["contract"] = CONTRACT[_sp["id"]]

if __name__ == "__main__":
    for sp in SPRINTS:
        n = sp["id"].split("-")[1]
        path = os.path.join(HERE, f"sprint-{n}-{sp['slug']}.src.html")
        with open(path, "w") as fh:
            fh.write(render(sp))
        print(os.path.basename(path))
