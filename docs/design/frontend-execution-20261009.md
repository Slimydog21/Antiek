# Frontend execution state, 9 October 2026

This is a selected source and evidence snapshot for coordinating the keyboard,
panes, Zen home, project gears, and agent monitoring work. It supplements the
local `specs/antiek-keyboard-panes-agents-20261007` handoff. It does not change its
requirements or replace the existing source holders.

The requested outcome remains a keyboard-first workstation with Omarchy-like
pane management across real reading, writing, and research surfaces; project and
cross-project agents beside that work; a simple multimodal project entrance;
recursive project and agent navigation; and truthful monitoring. A green
component branch does not demonstrate that composed journey.

## Evidence and baseline

`READ` means selected primary source. `OBS` means an observed state at the stated
time. `INF` means an inference from the cited source. The source audit itself used no candidate execution. Separately authorized
keyboard verification and its narrower evidence scope are recorded below.

- OBS, 09:33 UTC: GitHub main is
  `d0bee39aefd09c115b337467b9ee4a4da4e523c1`, tree
  `d8f383b2236ac8fdc1ca84cee427144de4a7fad1`.
- OBS, 09:02 UTC: an owned anonymous browser context received HTTP 200 JSON from
  `https://api.antiek.ai/health`, with that exact build, schema 41, status `ok`,
  and `providers_ready: true`. The context was disposed. This is backend health,
  not a signed catalogue, reading, or provider invocation.
- OBS, 08:58 UTC: the public frontend redirected `/` to `/login?next=%2F` and
  rendered its email/passkey entrance. Its actual frontend build identity was
  not bound. This is not an authenticated workspace observation.
- READ/OBS: AgentPane PR #3756 was merged as `d545009e`; that commit is an
  ancestor of the pinned main. Its implementation is present, but the complete
  project-to-agent and every-island journey remains unproved.

The following are independently observed PR heads at 09:29 UTC. The later
keyboard successors are recorded below; this dated table is not overwritten.
Check counts are
reported contexts observed at 09:03 UTC, not a fresh required-policy certificate.

| Unit | Head | State | Reported completed contexts |
| --- | --- | --- | --- |
| Zen home #3749 | `6be2f59a10085e43f5e7c9e0064d01d285ecdc22` | Open | 15 success |
| Pane flow #3754 | `c2468e6cac99e8d6f6816d144806d36a09fe9d08` | Open | Only one Cloudflare Pages success |
| Geared switcher #3757 | `00af0384d592cc08d3a637e12f9108dcf3794bba` | Draft | 15 success |
| Agent monitoring #3758 | `481e5ba364f3e9810bf82a02e40a65e1846a214d` | Draft | 15 success |
| Private KeySheet #3784 | `4fef92c8a91b89fa8cfcf111ffc5a71d07a83fc4` | Open, merge held | 15 success |

The old sprint index contains dated branch heads and a #3756 draft status. Those
entries describe the earlier snapshot. They are not current ownership or agent
liveness evidence, and must not trigger duplicate work.

## Preserve and reuse the current contracts

READ: main, the typed-tree #3752 head, and geared #3757 share the existing tree,
selection, tree store, and pre-backend adapter blobs. Reuse the actual interfaces;
an open historical PR does not mean its core contract files are absent.

The shared pre-backend adapter blob is
`787a91fa6405d1bf492fad9fb9d0214d8c8bd7ce`. Monitoring #3758 also consumes it.

READ: the Zen candidate keeps `PROJECT_SEED_CONTRACT_LIVE = false`. Its default
intake starts an investigation, returns its ID as both project and investigation
ID, and marks the registry step `skipped-pre-contract`. The Zen submit handler
discards the returned `CreatedProject`, and its route supplies no switcher slot.
The conditional real-project branch already uses `createProject` and
`addProjectMember`. See
[the exact intake](https://github.com/Slimydog21/Antiek/blob/6be2f59a10085e43f5e7c9e0064d01d285ecdc22/apps/reading/src/modes/Home/useProjectIntake.ts#L188).

READ: the production tree hook accepts a member map in its composition model but
does not fetch or pass it. Its registry cache is keyed by owner epoch and lacks a
same-owner creation refresh. See
[the exact feed](https://github.com/Slimydog21/Antiek/blob/d0bee39aefd09c115b337467b9ee4a4da4e523c1/apps/reading/src/workspace/contracts/adapters/preBackend.ts#L306).

INF: the smallest coherent join is authoritative created project identity,
existing registry member edges, a fresh typed feed, then the existing selection
writer. Do not create a second registry, relabel an investigation as a durable
subproject, or flip the seed flag before its authentic backend contract exists.

## Pane flow is a defined host set

READ: the candidate mounts `PaneFlowLayout` around PanelLayout and WindowsLayer,
while the gate defaults off. Admitted targets are `core`, compound `companion`,
and live `window(id)` hosts. Individual dock panels and the reading ThreadIsland
are not separate pane hosts. Phone `sm` disables effective flow. Existing focus,
editing, IME, dialog, overlay, pointer, current-host, visibility, and geometry
refusals must remain.

One conditional dispatcher path needs its existing holder's control: the root
branch calls `togglePaneArrangementAt` before the flag-off fallback, while the
root is always mounted and that function has no flag check. See
[the exact dispatcher](https://github.com/Slimydog21/Antiek/blob/c2468e6cac99e8d6f6816d144806d36a09fe9d08/apps/reading/src/workspace/shortcuts.ts#L561).
This is source reasoning, not an executed failure or permission to patch a
foreign candidate. The single preview check is not the full gate.

Every-island completion still requires actual body/provider, parent geometry,
local widget priority, and host continuity boundaries. A windows-only result
would narrow the operator's requirement.

## Monitoring has a real mount and incomplete operational joins

READ, exact #3758 head: AppShell mounts `AgentMonitor` and `AgentGoto`. The lazy
monitor feed starts the real status store, list polling, toasts, and
`PreBackendTreeFeed`. The workspace attention badge and goto rows consume these
observations. This is mounted candidate source, not merely a story or export.
See [the mount](https://github.com/Slimydog21/Antiek/blob/481e5ba364f3e9810bf82a02e40a65e1846a214d/apps/reading/src/AppShell.tsx#L218)
and [the feed](https://github.com/Slimydog21/Antiek/blob/481e5ba364f3e9810bf82a02e40a65e1846a214d/apps/reading/src/workspace/agents/AgentMonitorFeed.tsx#L30).

Three separate joins remain:

1. **Target project to selected project.** The run entries contain project/group
   identity, but `GotoRow` and `FocusTarget` omit project identity. `focusAgent`
   activates or opens the companion view, focuses the right pane, and marks the
   run seen. It does not select a project. CompanionPane still filters by the
   selected project and renders `HiddenAgentPlaceholder` when that active view
   belongs elsewhere. INF: cross-project goto can land on the placeholder rather
   than the actual instance. See
   [focusAgent](https://github.com/Slimydog21/Antiek/blob/481e5ba364f3e9810bf82a02e40a65e1846a214d/apps/reading/src/workspace/agents/focusAgent.ts#L11)
   and [the filter](https://github.com/Slimydog21/Antiek/blob/481e5ba364f3e9810bf82a02e40a65e1846a214d/apps/reading/src/workspace/CompanionPane.tsx#L54).
2. **Actual blocked producer.** Derivation requires `raw.needsInput === true`.
   The real list producer never supplies that flag. The store seam and DEV-only
   injector are not production status evidence. Retain `unknown` where no
   authentic producer exists; do not fabricate a blocked transition.
3. **Freshness and errors.** List polling retains previous rows on error, but
   the adapter passes only investigations to the status store. Unchanged status
   fields do not update its stored `observedAt`; rows leaving the list window
   retain old observations. Attention and goto rows expose no age or error
   field, and the inspected derivation applies no age cutoff. This does not
   establish fresh status after a failed poll.

The monitoring trace selected 18 bodies, 168,357 bytes, from exact GitHub commits
without fetching refs. It is not a whole-PR semantic verdict. Reconcile these
joins with the existing monitoring, typed-tree, and companion holders before
writing a successor.

## Keyboard successors and fresh gate boundary

OBS, 10:20 UTC: Root's exact serial fixture allocation `92d58bc0` was executed,
custom first and KeySheet second, each under its own fresh 1,800-second clock.
Both ONE terminals were frozen and returned on the existing coordination routes.
Return is not Root intake, whole-source acceptance, or permission to merge.

### Custom hotkeys

The immutable prior attempt remains 119 pass and 8 fail out of 127, including its
late closure and diagnostic-accounting qualifications. Its 32 current account,
lifetime, and accepted-edit controls passed. The old fixture writer stacked waits
at the first matching render instead of placing one at each actual boundary.

The authorized correction relocates the same 39 canonical confirmation lines:
16 hook mounts, 4 AssignHotkey renders, 17 dispatcher installs, and 2 already
correct shortcut installs. Only three fixture files change; every non-readiness
byte and the fourth fixture are exact. Product and current control bodies are
unchanged by this fixture successor. Complete inverses restore the preimages.

Fresh selected Vitest passed **127/127**, with all 95 original and 32 current case
identities preserved and no failed/skipped/pending/todo case. Explicit strict
app and node noEmit both exited 0 with empty streams. Normal draft
[PR #3788](https://github.com/Slimydog21/Antiek/pull/3788) has head
`0a80c9c2a6913f45a8a26d693f6ad4150ed42bce`, tree
`ce7f6cf96e9f091052a34b5434c09bd165244c15`, sole parent `a7cd7c4b`.
All 6,013 unallocated committed tuples are preserved. Keep accepted-edit
retention through same-token suspension without private I/O, replacement
refusal, and sibling/overwrite continuity.

### KeySheet

The immutable unpublished prior attempt remains 151 pass and 1 fail out of 152.
The four new and nine old account controls passed; the sole old failing case
expected private labels immediately after two synchronous renders.

The authorized correction adds only the canonical confirmation import, an async
case callback, and real confirmation within `act` after those two renders.
All original 6,775 bytes remain in order, including assertions, inputs and
fixtures. The whole inverse restores the preimage. Product and new controls
remain exact; an empty async `act` was not substituted for confirmation.

Fresh selected Vitest passed **152/152**, with all 148 original and four current
case identities preserved and no failed/skipped/pending/todo case. Explicit
strict app and node noEmit both exited 0 with empty streams. One normal nonforce
author push advanced existing
[PR #3784](https://github.com/Slimydog21/Antiek/pull/3784) from verified `4fef92c8`
to `fd9fcab9e390042bc7c816d2faa9d1f528ae28e0`, tree
`88ee364ffeda91522df19c6e8433d927b84deb31`, sole parent `4fef92c8`.
All 6,017 unallocated committed tuples and other protected source/config bodies
are preserved.

Each genuine locked/CAS registration observed 37 independently mapped foreign
missing-worktree errors in pre/candidate/post, with no own/new error and all
prior rows and unrelated fields exact. This is not global GREEN. KeySheet's
administrative wrong-filename and phase-ledger attribution failures are retained;
the clock was not renewed and no retrospective full-meter certificate is made.
Both matching private installations were retired by captured identity. Direct
process reap and stream EOF do not certify a complete loaded-origin or global
descendant census.

OBS, 10:20 UTC: fresh custom frontend checks succeeded while four Python shards
were in progress; fresh KeySheet hosted gates were in progress. Local counts are
synthetic UNIT evidence, not receiving, signed-account, provider, or browser
journey acceptance. Dated Doctor results were not rerun. Root retains FIRST
intake, whole-source/security/current receiving, complete fresh required gates,
and normal merge/deploy. Both author units are terminal; the wider goal remains
incomplete.

## Reference behavior checklist

The existing primary-source study of
[Omarchy navigation](https://github.com/omacom/omarchy/blob/quattro/manual/04-navigation.md)
covers direct launches, directional focus, swaps, float/tile behavior, workspace
movement, fullscreen levels, persistent layouts, groups, and scratchpad. Browser
chords differ because the desktop can consume Super, but the pane-management
outcome should be checked behavior by behavior.

[PostHog LemonButton](https://github.com/PostHog/posthog/blob/master/frontend/src/lib/lemon-ui/LemonButton/LemonButton.scss)
uses a 0.1875rem physical frame with distinct hover/press depth and compensating
shadow geometry; tertiary controls stay flat. Apply that hierarchy through
Antiek's existing tokens. Delight also depends on honest empty/error states,
explained disabled controls, keyboard discoverability, and interruption-free
loading, as the existing fun-mechanics sprint records.

The supplied [Grok reconstruction](https://github.com/b-nnett/grok-bot-0.18-reconstructed)
is explicitly unofficial with a partly reconstructed frontend. Use its qualified
interaction reference alongside Antiek's existing scoped CompanionPane; it does
not justify replacing identity, admission, draft, provider, or anchor contracts.

## Execution order and ownership

1. Root consumes the two completed keyboard successor terminals, reconciles
   receiving source, and requires their fresh whole gates. The fixture author
   work is complete; no failed slot or clock is replayed.
2. Existing Zen/backend/tree/gears holders agree the authentic identity/member/
   refresh/selection handoff. Then connect the Zen switcher slot.
3. Existing pane/dispatcher holder proves flag-off legacy behavior and the full
   required gate; resolve body/provider and parent/local-priority ports for the
   complete island set.
4. Existing monitoring holder carries project identity into attention navigation
   and receives authentic status/freshness inputs through the same typed feed.
5. Root selects the coherent receiving head and fresh security/full gates, then
   normally merges and deploys. After legitimate account and provider admission,
   prove a project-to-descendant-to-agent keyboard journey beside real reading
   or writing, including focus, resize, reorder, and return.

Themes owns the separate README acceptance-language repair. No shared dirty
checkout, foreign source, assertion, reservation, or goal status is changed by
this document. This is an ordinary operator-directed docs branch, not a reuse of
the bounded controller registration exception.

Not proved: current frontend build identity; authenticated composed Zen/gears/
panes/monitoring; every-island state and provider continuity; ordinary-account
agent/ASR operation; native AX parity; the full private reading/revisit journey;
or an exhaustive all-agent/all-source audit. The full Antiek goal remains active
and incomplete.
