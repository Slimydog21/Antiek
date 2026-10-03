# Design model — the three motherships (lane A, 2026-09-24)

Status: grounded. Every name below has since been pinned to main `15e78e276` by `ground/lane-a-*.json` and `GAPS.md`; the sprint pages carry the exact files.
Binding inputs: `DECISIONS.md` (D1–D6) and `research/` (herdr's own model).

## 1. The object model, herdr → Antiek

herdr gives the operator one mental model that already works across 20 workspaces and 252 tabs. Antiek
keeps the shape and changes what the leaves are.

| herdr | Antiek | Notes |
|---|---|---|
| session | account | One per login. It holds all three motherships, the shared workstation registry, and the attention inbox. |
| (no equivalent) | **mothership**: `Research`, `Writing` or `Reading` | D1 + D5: three shells over the same projects. A mothership is a *mode of work*, not a container of data. Switching mothership keeps the current workstation (project) and opens that project's tabs for the other mode. |
| workspace (`identity_cwd`) | **workstation** = project | The same workstation id in all three motherships. It is named, ordered and pinned, and carries its own active tab per mothership. The registry is shared (lane B owns the project entity; lane A owns its chrome). |
| tab (stable public number) | **tab**, a node in a **branch tree** (D6) | A tab holds exactly one *surface*: reader, research canvas / investigation, writing document, companion (D3), thread, or flag queue. Unlike herdr, tabs form a tree. Opening a footnote, reference, citation, island or deep research from a tab spawns a child tab, at unbounded depth. A workstation holds a forest; its root tabs play herdr's top-level-tab role. Numbers are hierarchical and stable (`3`, `3.2`, `3.2.1`), like herdr's `public_tab_numbers`, so a number always means the same tab until it is closed. |
| pane (split) | **pane** | At most two panes per tab in v1: a main surface plus one docked companion. That docked pane is the reader beside a document, the companion **rail** beside an evidence document (D3), or a thread beside the reader. The rail is not a floating window, so it never covers the text. |
| agent in a pane, with detected state | **subagent thread** | Lane B's thread (an investigation). Its state is `queued · running · needs-you · done · failed · stopped`, or `idle` for a reading thread, rendered the way herdr's sidebar renders agent state. A launch refused at the cap is `refused_capped` on the launch surface and in the inbox, never a thread state (THREAD-CONTRACT §1.1.4). |
| agent sidebar rows (quota tokens) | **workstation sidebar** | Lists workstations. Under the active one it lists live threads with state and spend (the BYOT balance/usage already on main via #3400). Toggled with `prefix+b`. |
| notification / "ask inbox" plugin (`alt+a`) | **attention inbox** | D4: a thread that finished, a thread that needs the user, a flag waiting for consent, a daily cap reached. The operator already uses an ask-inbox plugin in herdr, so Antiek's inbox follows its semantics: pending questions first. |
| goto picker (`prefix+g`) / keybind help (`prefix+?`) | **switcher** (`cmd+K`, `prefix+g`) / **key sheet** (`prefix+?`) | The switcher searches every workstation, tab, thread and document by title and number. At 174 tabs in one workspace, scanning is not navigation; search is. |

What stays unmodelled on purpose: herdr's arbitrary pane trees, resize mode and copy mode. A research
surface is not a terminal. Two panes is the ceiling that keeps reading legible. Each rejection is recorded
in the spec's "Rejected alternatives".

## 2. Keys (D2: herdr prefix + direct chords)

One keymap table is the single source of truth. The key sheet (`prefix+?`) renders it, and the same
table drives the `aria-keyshortcuts` attributes, so it can never drift from the handlers.

| Action | Prefix (default `ctrl+b`, configurable) | Direct chord (browser-safe) |
|---|---|---|
| Switcher (goto picker) | `prefix+g` | `cmd+K` / `ctrl+K` |
| Jump to tab 1–9 | `prefix+1..9` | `ctrl+alt+1..9` |
| Next / previous tab **in the focused pane** (left: document tabs; right: agent tabs, or block tabs in writing) | `prefix+n` / `prefix+p` | `ctrl+alt+]` / `ctrl+alt+[` |
| Pane focus: left / right (the two cockpit panes) | `prefix+h` / `prefix+l` | `ctrl+alt+h` / `ctrl+alt+l` |
| Fullscreen the focused pane (toggle; Esc restores from any focus) | `prefix+f` | `ctrl+alt+f` |
| Layout: cockpit inset ⇄ docked (rarely needed; the cockpit is the default) | `prefix+shift+i` | none |
| New tab (picker: reader, document, research, companion) | `prefix+c` | `ctrl+alt+c` |
| Close tab | `prefix+shift+x` | none; destructive actions stay behind the prefix |
| Reopen the last closed tab in the focused pane (undo within the 10 s hold; afterwards restore the most recent retired tab) | `prefix+shift+t` | none |
| Workstation navigation (list) | `prefix+w` | `ctrl+alt+w` |
| Next / previous workstation | `prefix+shift+n`? (see below) | `ctrl+alt+shift+]` / `ctrl+alt+shift+[` |
| Switch mothership (Research → Writing → Reading, same workstation) | `prefix+m` (cycles); `prefix+shift+m` opens a 3-way picker | `ctrl+alt+m` |
| Branch tree: parent / last child / tree panel | `prefix+u` / `prefix+o` / `prefix+t` | `ctrl+alt+u` / `ctrl+alt+o` / `ctrl+alt+y` (not `ctrl+alt+t`, which is Ubuntu/Fedora's "launch terminal") |
| Jump by hierarchical number (`3.2.1`) | `prefix+g` then type the number | `cmd+K` then type the number |
| Toggle sidebar | `prefix+b` | `ctrl+alt+b` |
| Toggle companion rail / docked pane | `prefix+r` | `ctrl+alt+r` |
| Island from selection (ask about this) | `prefix+a` with a selection | `ctrl+alt+a` |
| Attention inbox | `prefix+i` | `ctrl+alt+i` |
| Key sheet | `prefix+?` | none |

**Cockpit key decision (lane A, 2026-09-26).** Kimi's cockpit PRs (#3441/#3442) gave `n`/`p` to the right pane only, `i` to the layout preset, `c` to close (with a direct `ctrl+alt+c` chord) and `f` to pane fullscreen. Resolved against this table and the operator's Omarchy prompt:
- `n`/`p` act on the **focused** pane's tabs, as herdr's tabs belong to their pane. With neither pane focused, they act on the left, where the core material lives.
- `f` is pane fullscreen. It subsumes distraction-free reading and matches the operator's "fullscreen them" ask.
- `i` stays the attention inbox (D4). The layout toggle moves to `prefix+shift+i`, with no direct chord.
- `c` stays "new tab", and `ctrl+alt+c` stays its direct chord. Close stays behind `prefix+shift+x` alone: destructive actions never get a direct chord, so Kimi's `ctrl+alt+c` **close** chord is removed.
- The operator's example keys `cmd+←/→` and `cmd+F` belong to the browser (history and find), so the cockpit uses `h`/`l`/`f` with prefix and `ctrl+alt` twins.

Two conflicts are resolved in the spec, not here:
- herdr's `prefix+shift+n` means *new workspace*. Antiek either keeps that meaning or remaps it; herdr
  muscle memory argues for keeping it.
- `ctrl+b` inside the Writing editor. The prefix must never steal a key from a focused text surface where
  it has an editing meaning. On macOS `ctrl+b` is "cursor back one character" in text fields; bold is
  `cmd+B`.
Direct chords avoid plain `alt+digit`: macOS composes it into characters (`¡™£`) inside every text
field. herdr's own keyboard doc recommends the `ctrl+alt` family for exactly this reason.

**Pane behaviour, ratified from A1b (lane A, 2026-09-27).** These behaviours are in code and verified by render at 1440/1280/1024/900/390, light and dark (A1b stage B4). They are ruled here so later work can rely on them:
- **Below 1280 px.**
  - At lg and md, the inset layout keeps both panes. At md, the right pane narrows to 280 px; at lg, it keeps its token width. This follows forensic T10.
  - At sm (below 768 px), there is one pane, no strip and no pane keys, and h/l swap between the panes where a door has two (Speak).
  - The md left dock stays 0 px. Until that changes, prefix+b at md opens the project tree as an overlay, never as a dock you cannot see.
- **Fullscreen.**
  - `prefix+f` fullscreens the focused pane.
  - In the docked preset, with no dock open, it does nothing.
  - Opening a panel into a side that fullscreen hides exits fullscreen first.
  - A "Fullscreen · Esc" chip restores by pointer.
  - Both panes stay mounted throughout: route, drafts and listeners survive.
- **Pane focus ring.** The ring stays on the last focused pane when DOM focus leaves the cockpit, because it marks which pane n/p act on. Clearing it on blur is an operator call and is not made.
- **Late agent opens.**
  - An agent's request to open a document that resolves after the operator has navigated elsewhere spawns its left tab **without activating it**; the tab does not take the screen, and it shows in the strip with a quiet toast.
  - An open that resolves while the operator is still where they asked activates as usual.
  - This is the one rule for when opener-driven navigation may take the screen: only while the operator hasn't moved.

**Desktop-grab collisions (settled 2026-09-24, from MS-01's audit against herdr's avoid list).**
- `ctrl+alt+u` collides with Konsole only inside Konsole's own window, so it never reaches a browser. It stays.
- `ctrl+alt+a` is a global grab on KDE Plasma ("activate window demanding attention"), where the browser never sees it. It stays anyway:
  - the operator's machines are macOS and Omarchy (Hyprland), neither of which grabs it;
  - every direct chord has a prefix twin, so `prefix+a` always works.
- A browser can tell Linux apart but not which desktop it runs, so the key sheet cannot flag a KDE collision. It always lists the prefix twin beside the chord instead.
- The rule going forward: a direct chord is a convenience and the prefix is the guarantee. A chord is dropped only when it collides on the operator's own platforms, as `ctrl+alt+t` was.

## 2a. The branch tree (D6): legible at any depth

The tree is the operator's logic tree made visible. It is this design's single signature element: the one
place we spend boldness (frontend-craft §1.4). Everything around it stays quiet.

- **Path header.** A breadcrumb from the root document to the current tab (`1 Origin of Species › 1.3
  Lyell, Principles › 1.3.2 ch. 3`). Past about four crumbs it compresses in the middle (`1 › … › 1.3.2`).
  Clicking the ellipsis opens the full path. Every crumb is a link.
- **Sibling strip.** Under the path: the current tab's siblings in herdr style, plus a `↳ n` chip for the
  current tab's children. It never shows the whole tree; the tree panel does that.
- **Tree panel** (a sidebar section, `prefix+t` / `ctrl+alt+y` toggles). The whole forest of the
  workstation, as an outline with:
  - hierarchical numbers
  - a glyph per surface kind
  - a live state on thread tabs (running, needs-you, done)
  - an unseen dot where a branch has new results

  Indentation is capped visually at six levels. Deeper nodes keep a 6-level indent and carry a depth badge
  (`d9`). **Focus subtree** re-roots the panel on any node, and **up** restores the parent view. No depth
  is ever unreachable or illegible.
- **Branches from a document.** A deep research spun from a highlight, a link to another document
  and a Write citation traced to its source each open as a **child** of the tab they were triggered
  from, in that tab's tree (the route carries `?m=<tree>` when it belongs to another mode). Only a
  typed URL or a door on the nav rail seeds a root. Back or Forward to a closed branch's history entry re-spawns it as a child with its original origin, which keeps the logic tree intact (lane A, A1b).
- **Numbers as addresses.** The switcher accepts a hierarchical number: `3.2.1` + Enter jumps there. This
  replaces herdr's `prefix+1..9` for depth: `prefix+1..9` jumps among the root tabs; numbers reach
  everything else.
- **Tree keys:**
  - `prefix+u`: parent
  - `prefix+o`: last-visited child
  - `prefix+n` / `prefix+p`: next / previous sibling (herdr's next/prev tab)
  - `prefix+t`: tree panel

  Each key's direct-chord twin is in the keymap table.
- **Closing a branch.** Close offers two outcomes. **Prune**, the default, closes the tab and everything
  under it, as abandoning a rabbit hole should. **Close only this** lifts its children to its parent.
  Both undo for 10 s. `prefix+shift+x` prunes the active tab; in the tree panel, `Delete` on a row
  prunes and `Shift+Delete` closes only that tab (lane A repair round 1, 2026-09-26). This needs a new undo action on `LemonToast`: main has none, and its lifetimes are 4, 6 and 8 s. A pruned subtree stays recoverable from the workstation's history, because the
  path taken is itself evidence.
- **The tree is a record.** The branch tree is persisted (lane B), so a rabbit hole survives a closed
  laptop and a device change. The companion tab can show "how I got here" for any finding.

## 2b. The Reading mothership (D5)

Reading is entered by *what to read*, not by where it lives. Its home has three doors:
- **Continue:** books and documents in progress, with position and progress.
- **To read:** the queue of `read` flags set by the operator *or by an agent* (D4 flags with a `read`
  intent). Each item shows who flagged it, why, and for which project.
- **New:** library, search, import. A standalone book (use case i) opens in its own reading workstation,
  which can be linked into a project later (**Q-A5**). Opening a project's item (use case ii) opens it
  inside that project's workstation, so everything found while reading lands in that project's
  companion.

The bar is a Kindle, or a real book:
- typography from the W1 tokens and one prose layer (W3), with a 60–72ch measure
- page keys (←/→, space) and progress, with position synced across devices
- a distraction-free mode (`prefix+f`) that hides all chrome but the path header
- day and night themes
- no layout shift while text loads

A footnote, reference or citation opens as a **child tab** (D6), never a navigation away. `prefix+u`
returns to the exact passage.

## 3. Reading, everywhere (A2)

Reading is its own mothership (§2b) and also a surface any tab or pane can host. In Research and Writing:
- open an evidence document as a **tab** (full reading), or
- as the **docked pane** beside what you are writing or researching (read while you write),
- from any citation, claim, source card, notebook block or thread, **in place**: it opens in the docked
  pane, never by navigating away and losing the workstation.

## 4. Islands (A3)

A selection in any reader surface offers one quiet affordance, **Ask**. It opens an **island** anchored
to that span. An island is the smallest possible conversation with a subagent: it binds the selection +
document + workstation as context, chooses the model (the BYOT dropdown already on main), shows cost
before spend, streams process as well as outcome, and can be:
- **kept**: collapsed to a margin mark on the passage, reopenable,
- **promoted**: opened as a thread tab, when it grows beyond a margin conversation,
- **merged**: its context joined into another thread (lane B's merge engine).

"Ask without a highlight" is the same island, opened from the switcher or `prefix+a` with nothing selected.
Its context is then attached by hand: documents, notes, and existing threads, which the switcher can
search.

Physics (the PostHog bar): an island hinges out of its anchor (the Popover `rotateX` hinge, origin at the
anchor edge), never covers the anchored text, and returns focus to the passage when closed.
Reduced-motion users see a plain appear. At 390 px an island becomes a bottom sheet.

## 5. Threads, merge, fork (A4)

- **Thread list.** Per document (the margin marks plus a list in the rail) and per workstation (the
  sidebar and a Threads tab). Each row shows its state, anchor, model, spend and last activity.
- **Ask this thread.** Any thread row opens a follow-up composer that continues *that* investigation
  with its held context. Lane B contract: "ask this thread" continues or chases the investigation, with
  its trajectory as context.
- **Merge.** Select two or more threads and choose Merge. A preview shows which claims and sources come
  from which thread, and conflicts are shown, never averaged away. Accept produces a merged thread with
  lineage. Automatic merge (lane B) surfaces as a suggestion in the inbox, never silently.
- **Merge into document → fork.** From a thread outcome or a companion entry, choose "merge into…" a
  writing document. The result is a **fork** with lineage, shown as a diff you accept or discard; the
  original is untouched. Lane B guardrail: it reuses the HTML-projection fork lineage and Write documents.

## 6. Companion (D3)

- **Companion tab** (per workstation): the human-facing account of what the project's subagents found.
  Claims, open questions and key insights, each with outcome first and process one click deep.
- **Companion rail** (per evidence document): the same derived companion filtered to this document.
  Margin marks connect to rail entries both ways.
- The **agent-facing evidence base** is lane B's richer store. Lane A renders only a link to it ("what
  the agents see"), never a second copy.

## 7. Autonomous diligence (D4)

A **flag** can be set on a passage, a claim, an open question or an insight. Flagging offers "Diligence
this". Consent shows the model, an estimated cost, and today's remaining cap. Accepted flags queue as
threads (state `queued`), run under the daily cap, and report to the attention inbox. A launch refused at
the cap reads `refused_capped`, with a one-step "raise today's cap" action; a run the cap halts mid-flight
reads `stopped`. Nothing runs without per-flag consent.

## 8. Craft bar (applies to every surface above)

Every surface ships with all of its states designed: loading, empty, error (with retry), partial, refused,
offline. None states a zero or an empty list from an unknown; this is the rubric veto that W7 closed on
five pages.
- **Keyboard:** every action has a key and a visible path; focus returns on close.
- **Contrast:** AA in both themes (the W1 tokens).
- **Motion:** reduced-motion respected (the W5 heartbeat).
- **Budget:** the entry bundle stays under its 700 KB gz budget. New surfaces load lazily; W7 showed how.
