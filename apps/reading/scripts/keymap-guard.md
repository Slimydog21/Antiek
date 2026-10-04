# Global keymap guard

Run from `apps/reading`. Requires `npm ci`, browser-harness, and a disposable Chromium CDP endpoint.

```sh
npm run guard:keymap:serve
# In another terminal, with BU_NAME and BU_CDP_URL selecting the disposable browser:
npm run guard:keymap
npm run guard:keymap:sensitivity
```

The fixture server binds 127.0.0.1:5196. It serves the real app entry, router,
AppShell and lazy surfaces. Only HTTP data is fixture data. It has no proxy to
an operator backend. The fixture prepares stores; it never replaces action
handlers. The browser driver uses trusted CDP keys and checks both ownership
traces and visible effects. Every active KEYMAP alias runs on Mac and other
platform semantics, then in a text field. This is not a physical OS layout test.

`validateKeymap` checks actual handler keys, executable action scenarios,
pressed row IDs and the actual rendered sheet. The scenario map is typed by
ActionId. No copied list decides which table rows to exercise. A scenario
whose action loses its last table row also fails. Removing one equivalent alias
from both the table and sheet changes the declared population; without an
independent signed inventory, this gate cannot infer that such removal was wrong.

Every top-window/document keyboard registration uses `registerKeyboardOwner`
with owner ID, scope and event eligibility. Its trace is read-only and records
instances, so duplicate mounts remain visible. Prefix capture precedes bubble
owners. Passive observers do not compete. Exclusive modal instances can each
register Escape; their `topModal()` predicates decide eligibility. The AST gate
rejects undeclared native global registration, including global aliases,
computed property names and key-event assignments. An iframe's own document,
element React handlers, editor plugins and native browser keys are outside this
population. This guard does not certify every local keyboard handler.

An implemented row requires a handler and an observable action scenario.
An unimplemented row requires `blockedBy`, no handler, and a pressed alias that
leaves the observed app state unchanged. Unimplemented is not a skip or an
allowlist. The key sheet derives its pending set from KEYMAP.

`blockedBy` is a manual authority reference. It can become stale without a
failure. There is no signed machine-readable acceptance state for the created-owner
authority. A merged commit or an OpenAPI path alone cannot establish deployment
and owner-gated behavior. A future status check would need the authority's
accepted commit plus deployed build SHA and cross-owner live acceptance result.
This guard does not invent those facts.

Sensitivity mutates the real source and restores it in `finally`. Each mutant
must fail with its own row/action/owner name. Guard-file hashes prevent a mutant
from changing its judge. The navigation-race mutation requires the race repair
from commit 71437e0a1980ffa76ad56e7c7ae46f6909471279 (or its accepted equivalent).
Its deterministic scheduling regression uses jsdom and synthetic key events;
the alias/effect matrix uses trusted browser keys. The race schedule itself is
not claimed to be reproduced by physical browser input.
