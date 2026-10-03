# Research inputs (lane A)

- `herdr-keyboard-v0.9.1.mdx` — herdr's own keyboard doc, fetched 2026-09-24 from
  https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/keyboard.mdx
  Defaults: prefix `ctrl+b`; `prefix+c` new tab; `prefix+n/p` next/prev tab; `prefix+1..9` jump to tab;
  `prefix+w` workspace navigation; `prefix+g` goto picker; `prefix+b` toggle sidebar; `prefix+shift+n` new
  workspace; `prefix+?` keybinding help with `/` filter. Direct chords: herdr recommends the `ctrl+alt`
  family (plain `alt` chords are composed into characters by macOS option-key handling).
- `herdr-operator-session-shape.json` — the operator's live session: 20 workspaces and 252 tabs; the largest workspace has 174 tabs (so tab overflow, a searchable tab picker and numbering past 9 are required),
  workspace keyed by `identity_cwd` with stable public tab numbers.
- Operator config: `~/.config/herdr/config.toml` (custom plugin chords: alt+g/r/a/d/u, ctrl+shift+r/p,
  prefix+ctrl+s/r, prefix+shift+r).
