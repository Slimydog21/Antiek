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
   1–9, n/p, c, w, m, u, o, t, f, r, a, i, shift+x, shift+n) to MS-03 and MS-04. `keymap.ts`
   reserves them so that no row takes one for another meaning first.
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
- **Collisions to settle when the keys land.** herdr's avoid list names `ctrl+alt+u` (Konsole),
  `ctrl+alt+a` (KDE attention) and `ctrl+alt+t` (the terminal launcher on Ubuntu and Fedora).
  DESIGN-MODEL already moved the tree panel to `ctrl+alt+y`; the owning sprint must settle `u`
  and `a`. On Linux the Write editor's own `Mod-Alt-1..6` headings share keys with the planned
  `ctrl+alt+1..9` tab chords. The dispatcher leaves any key the editor handled first alone,
  so the editor wins inside it.
- **A cross-origin iframe** (the arXiv embed) never passes its keys to the page, so no key
  reaches the keymap while focus is inside one. Focus leaving the window disarms the prefix.

## Reconsider if

- the operator stops using herdr as the daily driver, or asks for one-step keys only. The
  ⌘⇧ scheme above is the ready fallback, and the table can express it without code changes;
- telemetry or the operator's own report shows the prefix is armed by accident, for example
  from a stuck chip or a lost first keystroke;
- a browser starts reserving a `ctrl+alt` chord that the table uses.
