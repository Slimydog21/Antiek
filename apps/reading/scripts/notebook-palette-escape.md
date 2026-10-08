# Notebook slash menu and palette Escape contract

Run from `apps/reading` after `npm ci`:

```sh
npm test -- src/modes/Notebook/SlashMenu.palette.test.tsx
npm run guard:keymap:serve
# In another terminal, with a lane-specific BU_NAME and a disposable CDP browser:
browser-harness < scripts/notebook-palette-escape.py
```

`D2_ESCAPE_URL` overrides the default `http://127.0.0.1:5196`. Use only the
isolated `guard:keymap:serve` server. The browser check clears that origin's
local storage. It uses the real app entry, router, dispatcher, notebook editor
and command palette. Only HTTP data comes from the existing fixture server.
No production backend or account is exercised.

The browser check opens a notebook through the palette, types `/`, opens the
palette again, and sends two trusted Escape keys at 1440 by 900. It requires:

- First Escape: only `palette.escape` is eligible and receives the key.
  The palette closes, the slash menu stays open, and focus returns to the editor.
- Second Escape: only `notebook.slash-menu` is eligible and receives the key.
  The slash menu closes.

The component regression also checks both platform modifier conventions,
both listener registration orders, the palette's existing clear-filter-before-close
rule, and slash Arrow/Enter suppression while the palette is open.

## Bounded coverage

This is a regression for one declared local-overlay/global-overlay pair.
It does not certify all local React handlers, editor plugins, or every overlay
combination. `notebook.slash-menu` already uses `registerKeyboardOwner`; the
existing diagnostics can observe its conflict without changing the registration
seam. The global guard's action population does not open this local menu.

A guard extension can add this pair as a named finite-context scenario beside
its stacked-dialog scenario. Keep the global KEYMAP row population separate
from that explicit scenario list. Report which local owner/context pairs ran,
and which remain untested. Do not describe that list as an inventory of every
local handler. This repair does not change the global guard or its declaration.

The two governing D2 documents require single global ownership and focus-scope
checks but do not order this particular overlay pair. The repair chooses the
smallest yield: while the palette is mounted, the slash menu claims none of
its keys. It preserves the menu and selection rather than closing them on open.
