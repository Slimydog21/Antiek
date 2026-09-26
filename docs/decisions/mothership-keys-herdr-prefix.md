# Mothership keys: a herdr prefix plus ctrl+alt chords (D2 supersedes SPR-08's no-leader rule)

**Date:** 2026-09-24
**Decided by:** the operator, in the mothership htmlspec interview (recorded as D2 in
`specs/antiek-mothership/DECISIONS.md` by Antiek Nudge v2, session 236c36bd)
**Implemented by:** MS-01, branch `design/mothership-01-shell-keymap`
**Table:** `apps/reading/src/components/hotkeys/keymap.ts` (every D2 and herdr-default row cites this file)
**Status:** ratified. It supersedes one rule of the ratified SPR-08 command scheme; the rest of SPR-08 stands.

## Decision

The app has one keymap, one table and one dispatcher, and it answers to three kinds of key:

1. **A prefix, herdr style.** The default prefix is `ctrl+b`, herdr's own, and it is
   configurable. Pressing it arms the prefix and shows a quiet "prefix armed" chip. The next key
   goes to the keymap, and nothing else sees it. The prefix stays armed until that key or Esc,
   with no timeout, as in herdr and tmux. It never arms while focus is in a text field, the Write
   editor or a dialog, because `ctrl+b` means "back one character" in macOS text fields. MS-01
   binds `prefix+g` (the switcher), `prefix+?` (the key sheet) and `prefix+b` (the sidebar,
   today the project tree). DESIGN-MODEL §2 and §2a assign the rest of the prefix keys (tabs
   1–9, n/p, c, w, m, u, o, t, f, r, a, i, shift+i, shift+x, shift+n) to MS-03 and MS-04.
   `keymap.ts` reserves them so that no row takes one for another meaning first. The cockpit
   keys below took some of them on 2026-09-26.
2. **Direct chords in the `ctrl+alt` family.** They are matched on `KeyboardEvent.code`, the
   physical key, never on the character the OS composed. Every prefix action also has a
   one-step key: `ctrl+alt+b` for the sidebar, ⌘K for the switcher, and the lone `?` for the
   key sheet.
3. **The SPR-08 ⌘ combos, unchanged.** These are ⌘K, ⌘⇧P, ⌘J/E/Y/U/O/I, ⌘G, ⌘;, ⌘[ ⌘],
   ⌘W, ⌘/, ⌘B and `?`, and each is a `legacy-SPR-08` row. The one change: off the Mac, `mod`
   is Ctrl, so the old ⌘B would be `ctrl+b`, the prefix. There the project tree is reached
   with `prefix+b` or `ctrl+alt+b`, and the ⌘B row is Mac-only.

The key sheet (`prefix+?` or `?`) and every bound control's `aria-keyshortcuts` are generated
from the same table, so they cannot drift from the handlers.

## What was rejected, and why

- **SPR-08's no-leader rule** (`specs/antiek-mountain-shell-v2/sprint-08-hotkeys-command-scheme.html`,
  out of scope: "Leader keys, ⌥-prefixed namespaces, a command-mode"). Its reasons were real:
  a one-step key needs no mode to learn, and the old g-chords failed silently on an 800 ms
  timing window. Two things changed. First, the operator now lives in herdr, whose whole model
  is a prefix, so herdr muscle memory is the point. Second, the mothership addresses workspaces
  of up to 174 tabs, and no set of single keys covers that. A prefix plus the switcher does.
  The failure SPR-08 cited is designed out: this prefix has no timing window, and a visible
  chip shows while it is armed.
- **Plain `alt` chords** (`alt+1` for tab 1, and so on). macOS composes option+key into
  characters: `alt+1` arrives as `e.key === "¡"` and types "¡" into every text field. herdr's
  keyboard doc (v0.9.1, `specs/antiek-mothership/research/herdr-keyboard-v0.9.1.mdx`) maps the
  defaults of ten terminals and the GNOME/KDE globals and recommends `ctrl+alt` for this reason.
- **⌘⇧ letters only** (the refuter's MISS7: 22 ⌘⇧+letter combos are free and stay inside SPR-08's
  shape). That option means no mode and one keystroke fewer. It was rejected because 22 letters
  cannot address 174 tabs or a hierarchy of numbered branches (D6), because letters under ⌘⇧
  carry no herdr meaning, and because ⌘⇧ digits are unsafe (with shift held, `e.key` is the
  shifted glyph).

## Who pays

The one-handed ⌘ user: a prefix is two steps where ⌘ was one. That is why every prefix action
also has a `ctrl+alt` chord, and why the ⌘ combos keep working.

## Known limits

- **AltGr.** On Windows and Linux layouts that type characters with ctrl+alt (AltGr), a real
  AltGr press reports the `AltGraph` modifier and is never taken as a chord. Whether a *left*
  ctrl+alt on such a layout also reports `AltGraph` in every browser was not measured.
- **Desktop collisions, settled (DESIGN-MODEL §2, 2026-09-24).** herdr's avoid list names
  `ctrl+alt+u` (Konsole), `ctrl+alt+a` (KDE attention) and `ctrl+alt+t` (the terminal launcher on
  Ubuntu and Fedora). `ctrl+alt+u` collides only inside Konsole's own window, so it never reaches
  a browser, and it stays. `ctrl+alt+a` is a KDE Plasma global grab; it stays too, because the
  operator's machines (macOS, Omarchy/Hyprland) do not grab it and `prefix+a` always works. The
  tree panel moved to `ctrl+alt+y` because `ctrl+alt+t` launches a terminal on the operator's
  own platform. A direct chord is a convenience; the prefix is the guarantee. On Linux the Write editor's own `Mod-Alt-1..6` headings share keys with the planned
  `ctrl+alt+1..9` tab chords. The dispatcher leaves any key the editor handled first alone,
  so the editor wins inside it.
- **A cross-origin iframe** (the arXiv embed) never passes its keys to the page, so no key
  reaches the keymap while focus is inside one. Focus leaving the window disarms the prefix.

## Cockpit keys (lane A, 2026-09-26)

**Decided by:** lane A, resolving the cockpit PRs (#3441, #3442, #3443, #3444) against
DESIGN-MODEL §2 and the operator's Omarchy prompt ("two tall rectangles next to each other";
"keys at a project level and a document level, like tabs"). **Implemented by:** stage 3 of the
cockpit rescue, branch `design/cockpit-a1-d6c5-rescue-20260926`.

Those PRs took four keys that DESIGN-MODEL §2 had already given to other actions. `i` went to
the layout preset, though it is reserved for the attention inbox. `c` became close, though it is
reserved for new tab, and it came with a destructive direct chord, `ctrl+alt+c`, that fires even
inside text. `n`/`p` went to the right pane only. Then a fourth pair, prefix `,`/`.` with
`ctrl+alt+,`/`.`, appeared when the document tree took `n`/`p` back. The table after this
decision:

| Action | After the prefix | Direct |
|---|---|---|
| Next / previous tab **in the focused pane** | `n` / `p` | `ctrl+alt+]` / `ctrl+alt+[` |
| New tab (picker) | `c` | `ctrl+alt+c` |
| Close tab (and its branches) | `shift+x` | none |
| Attention inbox | `i` | `ctrl+alt+i` |
| Layout: cockpit inset ⇄ docked | `shift+i` | none |
| Pane fullscreen (toggle) | `f` | `ctrl+alt+f` |
| Pane focus left / right | `h` / `l` | `ctrl+alt+h` / `ctrl+alt+l` |

- **`n`/`p` follow focus.** herdr's tabs belong to their pane, so the keys cycle the tabs of the
  pane that has focus. On the left that is the document tabs (the active tab's siblings). On
  the right it is the agent tabs, or the outline's block tabs in writing. With neither pane
  focused they act on the left, where the core material lives. In the docked preset a focused
  right-dock panel counts as the right pane. The rule is in one place, `shortcuts.ts`
  `tabKeySide`.
- **The `,`/`.` pair is removed.** It existed only because `n`/`p` could not reach both panes.
  With focus deciding, one pair covers both, and a second pair would be a key the D2 table never
  contemplated.
- **`c` and `i` are held for their surfaces.** The new-tab picker and the attention inbox have
  not shipped. Their keys are table rows whose handlers do nothing and return "not mine", so the
  dispatcher never swallows `ctrl+alt+c` or `ctrl+alt+i` from the page. The key sheet shows both
  rows marked "Not built yet" (`keymapView.ts` `PENDING`), so the operator can see what the key
  is for instead of meeting a dead key.
- **Close is `prefix+shift+x` alone.** Destructive acts stay behind the prefix, so no direct
  chord closes a tab. The key performs §2a's default outcome: the tab and everything branched
  from it (prune), held locally for 10 s behind the toast's Undo. §2a's second outcome, "close
  only this" (children lift to the parent), lives in the tree panel (`prefix+t`), where the
  outcome can be seen before it is chosen: on a focused row `Delete` prunes and `Shift+Delete`
  closes only that tab. Both undo for 10 s. These are plain keys inside a focused tree widget,
  not global chords, so the "destructive acts stay behind the prefix" rule holds. The panel
  takes focus when it opens and closes on a press outside it (repair round 1).
- **Esc restores fullscreen from any focus.** The restore listens on the document while a pane
  is fullscreen, not on the layout root, so Esc works with focus on `<body>`. Esc inside a text
  field or a dialog stays theirs. Right-pane fullscreen fills the cockpit; it no longer keeps the
  companion's 320 px column (repair round 1).
- **The layout preset moves to `prefix+shift+i`, with no chord.** The cockpit is the default, so
  the toggle is rarely needed.
- **`f` stays pane fullscreen and `h`/`l` stay pane focus.** Both match Omarchy. The operator's
  example keys `cmd+←/→` and `cmd+F` belong to the browser (history and find).

**Who pays.** A docked-preset user who reached the preset by `prefix+i` or `ctrl+alt+i` now
presses `prefix+shift+i`. Anyone who used `prefix+c` to close now uses `prefix+shift+x`, which
removes the whole branch rather than lifting its children, with the same 10 s Undo. Companion
cycling on `,`/`.` becomes: focus the right pane (`prefix+l`), then `n`/`p`.

**Reconsider if** focus-following `n`/`p` surprises the operator in practice, for example a
stale focus ring sending the keys to the wrong pane. The fallback is DESIGN-MODEL's original
split: `n`/`p` for the left, a second pair for the right.

## Reconsider if

- the operator stops using herdr as the daily driver, or asks for one-step keys only. The
  ⌘⇧ scheme above is the ready fallback, and the table can express it without code changes;
- telemetry or the operator's own report shows the prefix is armed by accident, for example
  from a stuck chip or a lost first keystroke;
- a browser starts reserving a `ctrl+alt` chord that the table uses.
