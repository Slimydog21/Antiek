# Speak Private↔Public spine & honesty contract

**Date:** 2026-06-04
**Branch:** `caffen/speak-spr01`
**Source spec:** Antiek Speak — Private ↔ Public Remembrance Spine, SPR-01
("Spine & honesty contract"). The full sprint page is
`specs/antiek-speak-private-public/sprint-01-spine-and-honesty-contract.html`.
**Status:** ratified contract. This document is the canon SPR-02..05 import.
A reader who opens **only** this file can start any Wave-2 lane sprint and
answer "why is the public lane locked, and what opens it?" without re-reading
the code.

This is the **authoritative** record of what Speak's private/public surface
ships today, the one defect that makes the public lane a dead-end, the
ratified payout basis, the human gate phrasing both lanes must use, and the
ownership boundary that keeps two parallel builders from colliding on the
shared shell.

> Scope note: SPR-01 itself produces (a) this doc, (b) the frozen `SpeakIndex`
> shell + the two extracted lane files, (c) the shared vocabulary module, and
> (d) the gate-honesty contract test. This file is the M1 + M6 artifact (the
> reconciliation audit and the published ownership handoff). The other
> milestones (M2 shell-freeze, M3 vocab, M4 payout-guard comment, M5 test) are
> code owned by sibling units; this doc *names* their outputs as the
> enforcement, it does not re-implement them.

---

## State map — what ships today, with line refs

Every row is traced through the **real code in this worktree**. The
`verified-by-read` column distinguishes a finding I confirmed by reading the
cited lines from one I inferred from surrounding context. Status ∈ {works,
broken, dishonest-by-omission}.

| Capability | file:line | Status | verified-by-read |
|---|---|---|---|
| **Yours tab** (private dashboard of people you're remembering) | tablist + dispatch in the shell `apps/reading/src/modes/SpeakIndex/index.tsx:170-206` (the `tab === "yours"` branch renders `<YoursLane/>` at `:202-203`); the tab body lives in `apps/reading/src/modes/Speak/lanes/YoursLane.tsx:24-69` (the person-card list) → `listPeople()` → `GET /speak/projects` (`speakApi.ts:165-171`; `speak_routes.py` projects index) | **works** | verified |
| **Public feed** (browsable list of will-be-public projects) | tablist + dispatch in the shell `SpeakIndex/index.tsx:170-206` (the `tab === "public"` branch renders `<PublicLane/>` at `:204-205`); the tab body lives in `apps/reading/src/modes/Speak/lanes/PublicLane.tsx:27-72` → `listPublicFeed()` (`speakApi.ts:266-281`) → `GET /speak/feed` (`speak_routes.py:381-404`, `WHERE p.publish_intent = 'will_be_public'`) | **works** (the endpoint + the in-tab render are real; honest-when-empty) | verified |
| **"Add your memory" CTA** (the in-feed chime-in) | `Speak/lanes/PublicLane.tsx:60-64` — `<Link to={`/speak/${f.id}`}>` wrapping a `LemonButton` | **broken** (targets the authed operator console route, not an unauthenticated contribution door) | verified |
| **Token invite path** (the actual unauthenticated contribution door) | route `apps/reading/src/App.tsx:232` (`/speak/invite/:token`, before the `RequireAuth` catch-all) → `SpeakInvite`; token resolves via `GET /speak/invites/resolve` (`speak_routes.py:435-445`) | **works** (this is the real public door — the token is the credential) | verified |
| **Economics / gate read** (G2/G3 state surfaced read-only) | `speakApi.ts:70-85` (`EconomicsView` + the "NO close affordance" doc-comment at `76-79`) ← `getEconomics()` (`speakApi.ts:179-183`) ← `GET /speak/projects/{id}/economics` (`speak_routes.py:364-377`) ← `gate_status.public_publishing_allowed()` / `disbursement_allowed()` (`substrate/speak/gate_status.py:39-73`) | **works** (deny-by-default, no UI close affordance) | verified |
| **`release_payout`** (graded accrual → escrow, never disburse) | `speakApi.ts:296-318` (`releasePayout`) → `POST /speak/projects/{id}/release-payout` (`speak_routes.py:651-665`) → `accrue_contributions` into escrow (`substrate/speak/contributor.py:232-310`); disbursement always refused (`contributor.py:356`) | **works** (escrow-only; zero-buyer-safe; the §9 money model) | verified |
| **`open-public`** (flip a project to open public contribution) | `POST /speak/projects/{id}/open-public` (`speak_routes.py:448-453`) → `invitations.open_public_contribution` → G7-gated (`substrate/speak/invitations.py:58-64`, `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`); refuses 403 when unset | **dishonest-by-omission** at the UI: the endpoint correctly refuses (403) but **no surface tells a user the public ecosystem is a future state** — the feed implies "add your memory" works today | inferred (the 403 path is verified-by-read at `invitations.py:62`; the *omission* is a UI-absence judgment, not a single line) |

### What "works" means here

The capability does the honest thing for an **authenticated operator**: the
yours dashboard lists their projects, the feed lists will-be-public projects,
the economics view reads gate state without offering a close, and
`release_payout` accrues to escrow and never disburses. None of these rows is
softened — each is verified at the cited lines.

---

## The dead-end defect (rigor #1 — this is a defect, not "needs polish")

**The public lane dead-ends for anyone without an account.** A logged-out
friend or family member — exactly the person the public feed is *for* —
cannot reach the public lane at all. Two line refs prove it:

1. **The public tab + "Add your memory" live behind `RequireAuth`.** The
   public feed UI is rendered inside `SpeakIndex` (the `/speak` mode). In
   `apps/reading/src/App.tsx`, `/speak` is matched by the `RequireAuth`
   catch-all at **`App.tsx:237-244`** (`path="*"` → `<RequireAuth><AuthenticatedRoutes/></RequireAuth>`).
   The only unauthenticated Speak route is `/speak/invite/:token`, declared
   **before** the catch-all at **`App.tsx:232`**. So a logged-out visitor who
   lands on `/speak` is bounced to login and never sees the feed or its tab.

2. **"Add your memory" links into the authed console.** The public-feed
   body now lives in `apps/reading/src/modes/Speak/lanes/PublicLane.tsx`
   (**lines 27-72**); it renders each feed item's "Add your memory" button as
   `<Link to={`/speak/${f.id}`}>` wrapping a `LemonButton` (**lines 60-64**).
   `/speak/:projectId` is itself behind the same `RequireAuth` catch-all — it
   is the **authed operator console** for one project, not a contribution
   door. So even if a visitor somehow reached the feed, the CTA would route
   them into a page they cannot open.

**Why this is a defect and not polish:** the product's entire public premise
is "someone shares a remembrance publicly and others *who knew the person*
add what they remember." That second person is, by design, not an account
holder. The shipped lane structurally cannot serve them. The real
unauthenticated contribution mechanism **does exist** — `/speak/invite/:token`
(`App.tsx:232`), where the token is the credential — but the public feed never
mints or links such a token; it links to the authed `/speak/:id` instead. The
feed is real; the **bridge from feed → unauthenticated contribution is
missing**, and `open-public` (the flip that would even populate that bridge)
is G7-gated and silently 403s.

**This defect is SPR-03's to close** (PublicLane owns the feed + the CTA
target), within the gate honesty discipline below — the CTA must not promise a
door that the G7 gate has not opened.

---

## Payout basis (M4)

**The basis is §9.3 Option-B: `claim_confidence × (6 − source_tier)`,
accrued to escrow, never disbursed pre-gate.** This is not a new mechanism —
it reuses the existing ad-attribution Option B at claim granularity. Verified
at `substrate/speak/contributor.py:14-15` (the formula), `contributor.py:232-310`
(accrual to escrow), and `contributor.py:356` (disbursement always refused).
The shipped `release_payout` → escrow path is the **sole money model**:
`speakApi.ts:296-318` → `speak_routes.py:651-665` → `accrue_contributions`.

### Steelman of the rejected alternative (rigor #2): the per-second ad model

The per-second / timecode revenue model is genuinely attractive on its face.
It is the model the rest of the attention economy runs on: a remembrance that
plays as audio or video could, in principle, carry mid-roll ad inventory and
pay contributors **pro-rata to seconds-of-their-voice-played** — a clean,
intuitive "you contributed 12% of the runtime, you get 12% of the ad take"
story that a creator and a contributor both grasp instantly. It would also
sidestep the harder `claim_confidence × source_tier` math, which requires the
corroboration pass to have run and assigns money to *claims* rather than to the
plainly-countable *seconds* a person spoke.

**Why it is rejected — category error.** Speak's deliverable is a **text /
book** (the assembled biography draft; `assembleDraft` → `prose_text`,
`speakApi.ts:249-259`). There is no timed-media playback surface and no
timed-media ad inventory to sell against. A per-second model has nothing to
meter: the deliverable is read, not played, and a contributor's value is the
**information their voice corroborates** (a claim that two independent voices
attest is worth more than an uncorroborated aside), which is exactly what
`claim_confidence × (6 − source_tier)` measures. Pricing voice by runtime would
reward the person who talked the longest, not the person who said the most
load-bearing, best-corroborated thing — inverting the corroboration honesty the
whole surface is built on.

**Reconsider if…** Speak ever ships a genuine **timed-media deliverable** (an
audio documentary or video remembrance that *plays*) with real ad inventory
sold against playback. At that point a runtime-metered split becomes a
legitimate second model **for that deliverable only** — but it must be argued
against the corroboration-value basis, not assumed, and it must not retroactively
re-price the text biography. Until then: Option-B, escrow-only.

---

## Gate phrasing (the human, read-only contract)

Three operator-owned gates bound the public/money surface. **In the UI they
are read-only**: a gate phrase describes a *future state* and contains **no
verb the user can act on** (no "enable / unlock / activate / close the gate"
as a user action). Closing a gate is an **operator env action** (a deliberate
flag flip post-counsel), never something a rendered surface can do. The
EconomicsView already encodes exactly this discipline — the "NO close
affordance" doc-comment at `speakApi.ts:76-79`.

**`speakVocab.ts` `GATE_PHRASES` (`:79-101`) is the render source-of-truth.**
The sentences both lanes (and SPR-04's payout surfaces) actually render are the
exported `GATE_PHRASES` strings; the table below **reproduces them verbatim**,
not the other way round. If the rendered copy must change, change
`speakVocab.ts` first and re-copy it here — the doc tracks the module, the
module does not track the doc. (The strings below are byte-identical to the
`label` / `whenGated` values in `speakVocab.ts`.) They are future-tense, human,
and verb-free of user action:

| Gate (`GATE_PHRASES` key) | Backend signal (read-only) | `label` (verbatim) | `whenGated` (verbatim) |
|---|---|---|---|
| **G2 / G3** — public publishing (`publicSharing`) | `public_publishing_allowed()` ← `ANTIEK_SPEAK_PUBLIC_PUBLISHING` (`gate_status.py:39-54`) | Public sharing | Public sharing opens after a legal review (G2/G3). Until then a remembrance stays private to you and the people you invite. |
| **G2 / G3** — disbursement (`disbursement`) | `disbursement_allowed()` ← `ANTIEK_STRIPE_PROVIDER` (`gate_status.py:57-73`) | Contributor payouts | Contributor shares accrue to escrow now; money begins routing once the legal review clears (G2/G3). |
| **G7** — public ecosystem / open contribution (`publicEcosystem`) | `public_ecosystem_enabled()` ← `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM` (`invitations.py:58-64`) | Open public contributions | Open public contributions arrive after the ecosystem review (G7); for now, contributions come through your invites. |

**Forbidden in any rendered string:** the raw flag names
(`ANTIEK_SPEAK_PUBLIC_PUBLISHING`, `ANTIEK_STRIPE_PROVIDER`,
`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`), the substrate enums
(`will_be_public`, `private_never_published`, `multiply_attested`,
`publish_intent`, `in_progress`), and any user-actionable verb on a gate.

### The executable form of this contract (rigor #5)

This honesty discipline is not a code-review judgment a future builder can
quietly erode — it is a **mechanical test SPR-01 produces**, named so a
refactor cannot silently undo it:

> `apps/reading/src/modes/Speak/lanes/gateHonesty.contract.test.tsx`

It fails if **any** exported gate phrase matches a user-actionable verb
(`/enable|unlock|activate|close the gate/i` used as a user action), or if any
of `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM` / `ANTIEK_SPEAK_PUBLIC_PUBLISHING` /
`ANTIEK_STRIPE_PROVIDER` appears in any string the vocab module
(`apps/reading/src/lib/speakVocab.ts`) exposes for rendering. SPR-03 and
SPR-04 inherit this test; if either accidentally writes a "click to enable
public sharing" string, CI goes red. **The test is the contract.** Reference
it by name in any PR that touches gate phrasing.

> **Honesty note for SPR-03/SPR-04 reviewers — don't over-trust the green
> check.** The verb-ban is a **denylist of exactly four tokens**
> (`enable` / `unlock` / `activate` / `close the gate`, in
> `gateHonesty.contract.test.tsx:34`), **not** a general false-agency
> detector. A green test means "none of those four verbs slipped in" — it does
> **not** prove a new sentence is honest. A phrase like "tap here to go
> public" would pass the test while still promising false agency. So the test
> backstops the obvious regressions; it does **not** replace reading the new
> copy against the read-only discipline above.

**Reconsider if…** the operator decides a gate *should* expose a user-facing
action (e.g. a self-serve opt-in once counsel permits it). Then the reopening
**must start by changing `gateHonesty.contract.test.tsx`** — the guard is the
contract; the verb-ban is deliberate, not incidental.

---

## Vocabulary (the words both lanes must use)

The single source of rendered words is `apps/reading/src/lib/speakVocab.ts`
(M3) — or the already-existing translation layer in `speakApi.ts`. No rendered
component may contain a raw substrate enum; the translation lives only in
`lib/` (the copy-lint scans `modes/`, `shell/`, `components/`, never `lib/`).

- **Lane labels:** "People you're remembering" (yours) / "Public
  remembrances" (public) — verbatim as shipped in the shell tab buttons at
  `SpeakIndex/index.tsx:182` and `:195`, and as the single source in
  `speakVocab.ts` `LANE_LABELS` (`:47-52`). Note: the shell still hard-codes
  these two literals; `LANE_LABELS` is the single source for Wave-2 to
  **adopt** — the shell does not yet read from it.
- **Corroboration vocabulary** (enum→kind mapping at `speakApi.ts:156-161`,
  the kind literals at `speakApi.ts:57`; the short rendered words at
  `speakVocab.ts` `AGREEMENT_WORDS` `:56-67`): `multiply_attested` →
  **"corroborated"**; `contradicted` → kind `disagreement`, rendered as
  **"people disagree"**; otherwise kind `single`, rendered as **"one
  person"**. These short forms are aligned to the shipped Speak console
  (`apps/reading/src/modes/Speak/index.tsx:428-432` and the draft surface at
  `:483` "people disagreed"). **Never** "proven" or "true."
- **Publish state, in plain words:** `will_be_public` → "Will be shared
  publicly"; `private_never_published` → "Kept private" (shipped in the
  person card at `Speak/lanes/YoursLane.tsx:61`).
- **Gate phrases:** `speakVocab.ts` `GATE_PHRASES` (`:79-101`) is the render
  source-of-truth; the table above reproduces those `label`/`whenGated` strings
  verbatim.

**Reconsider if…** a lane needs a word the vocab module doesn't have. The fix
is to add it to `speakVocab.ts` **with a recorded reason in this doc's change
log** — not to inline a raw enum or a one-off phrasing in a lane component.

---

## Ownership handoff (rigor #5 — the doc must let a sprint start from this alone)

SPR-01 freezes the shared `SpeakIndex` tab shell and extracts each tab's body
into a thin lane file so the two Wave-2 lanes are built **in parallel without
colliding on the shell**. The shell carries a verbatim ownership comment
(M2). The boundaries below are binding.

| Sprint | Owns (may freely edit) | Must NOT touch |
|---|---|---|
| **SPR-02** (private lane) | `apps/reading/src/modes/Speak/lanes/YoursLane.tsx`; the invite flow (`Invites.tsx`) + the `SpeakInvite` invitee-landing component | The frozen `SpeakIndex/index.tsx` shell; `PublicLane.tsx`; `speakVocab.ts`; backend |
| **SPR-03** (public lane) | `apps/reading/src/modes/Speak/lanes/PublicLane.tsx`; the feed + search surface; the read-only gate-state surfacing (it **consumes** the gate phrases; it does not author them) | The frozen `SpeakIndex/index.tsx` shell; `YoursLane.tsx`; `speakVocab.ts`; the `gateHonesty.contract.test.tsx` assertions; backend gate logic |
| **SPR-04** (payout legibility) | The payout-legibility surfaces (making the §9 escrow promise visible — "shares set aside, paid after legal review"); consumes `EconomicsView` + the disbursement gate phrase | The payout math (`contributor.py`); the lanes' shell; the gate phrasing strings (consume only) |
| **SPR-05** (capstone) | Integration / end-to-end wiring across the two lanes; whatever the prior four leave as seams | Re-litigating any decision in this doc without a recorded reconsider-if trigger |

**Hard rule:** **neither lane sprint re-edits the frozen `SpeakIndex` shell or
`speakVocab.ts` without a recorded reason in this doc's change log.** The
shell carries `<YoursLane/>` and `<PublicLane/>` inside its existing tab
panels; a lane changes only its own body. This is the collision-avoidance
contract — the operator's parallel-stream tooling commits in big batches, so a
same-file edit on the shell from two sprints would collide.

**Reconsider if…** the extraction (M2) does not earn its keep — i.e. the shell
is not meaningfully cleaner after extraction, or the two lanes turn out not to
need independent ownership. In that case the M2 owner should propose reverting
to the single-file `SpeakIndex` and say so in the handoff, rather than keeping
an abstraction that buys nothing. (Steelman of the single-file choice: it is
simpler and avoids premature abstraction; the extraction is justified **only**
by the parallel-ownership need, not by tidiness for its own sake.)

---

## Open questions for the operator

1. **Should `/speak` get an unauthenticated, read-only public browse?** The
   cleanest fix for the dead-end is splitting the public feed onto its own
   unauthenticated route (sibling to `/speak/invite/:token`) so a logged-out
   visitor can browse public remembrances and reach a token-minted
   contribution door. This is a **routing change** (out of SPR-01's
   read-only scope) and is gated on G7 (`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`)
   actually opening. Raised here, not implemented. SPR-03 should not promise
   the public CTA before this is resolved.
2. **Does the public feed's "Add your memory" CTA need its own token-mint
   endpoint?** Today there is no endpoint that hands an unauthenticated
   visitor a contribution token from a feed item; the only token path is the
   operator-initiated invite. SPR-03 will need one (gated on G7) before the
   CTA can honestly work.

---

## What shipped vs what's gated (2026-06-04 capstone)

This closing section is the SPR-05 capstone reconciliation. It states what the
private↔public Speak spine **actually does today** — not what the upstream
sprints intended — so the operator can decide, from this doc alone, which env
flip opens each gated capability. Every claim below is traced to a surface or a
backend signal already cited earlier in this doc; nothing here is rounded up.

### Private lane — works end-to-end

The private lane is the shipped, working path. An operator can:

1. **Name a person** — one warm field ("Who do you want to remember?") →
   `createPerson()` → lands on the project (`SpeakIndex/index.tsx:99-113`,
   `Speak/index.tsx`). Subject status + publish intent default safely (unknown /
   **kept private**) behind Settings; they are never the first screen.
2. **Invite by token-link** — "Invite the people who knew them": one shareable
   link (`makeShareLink`) or invite-by-email (`Invites.tsx`). The link's token
   is the credential; no account is needed for the invitee
   (`Speak/index.tsx:290-346`).
3. **Unauthenticated consent with publish OFF by default** — the invitee lands
   on `/speak/invite/:token` (`SpeakInvite/index.tsx`), an unauthenticated,
   token-gated page. The prominent button grants **record only**; **publish is
   never the default** — it is a separate, affirmative opt-in button shown only
   when the invite asks for it (`SpeakInvite/index.tsx:109-133`, 242-271).
   Declining lands on a warm thank-you, never a dead end.
4. **Answer (voice-first, type fallback)** — a big tap-to-talk mic through the
   single shared voice owner, with an honest "couldn't turn that into words"
   fallback to typing when there is no model key (`SpeakInvite/index.tsx:318-387`).
5. **Voice arrives** — the operator's console polls and shows arriving voices,
   "what everyone agrees on" (framed **corroborated, never proven/true**), and
   the assembling draft, each with an honest empty/loading/failure state
   (`Speak/index.tsx:348-482`).

**Gratitude is emotional, not money.** The private person-card and lane carry
only warm, voice-count-grounded gratitude ("Their story is coming together —
N voices have added a memory"); because `split_applies == false` for a private
work, **no money/share/payout/earnings language ever appears**
(`YoursLane.tsx:63-78`; SpeakSettings shows "A private story isn't monetised, so
there's no contributor split" at `SpeakSettings.tsx:210-216`).

### Public lane — honestly LOCKED

The public lane is real, browsable, and **honest that open contribution is not
live**:

- **Open contribution opens after G7** (`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`). The
  G7 lock is **static copy** — there is genuinely **no front-end read of G7**
  (`getEconomics` carries only G2/G3). The lane renders the canonical
  future-tense sentence `GATE_PHRASES.publicEcosystem.whenGated` **verbatim** in
  a `role="note"` panel — a true statement, not a faked live read and not an
  invented endpoint (`PublicLane.tsx:179-194`; rationale in the gate-phrasing
  section above).
- **G2/G3 publishing + payout state is read LIVE** via `getEconomics()`. The
  explainer's publishing and payout lines branch on the live, global-per-project
  gate state — gated future-tense copy when denied, an honest "now open" state
  sentence when the gate has cleared — and **deny-by-default** on any fetch
  failure or empty feed (`PublicLane.tsx:56-89`, 216-227).
- The "Add your memory" CTA links the **authenticated operator** to their own
  public-intent project (the correct working action behind `RequireAuth`); the
  copy is explicit that open contribution by strangers isn't live yet
  (`PublicLane.tsx:158-173`, `PUBLIC_LANE_LABELS.ctaOperatorOnly`).

### Publishing + disbursement — gated on G2 + G3

Publishing a remembrance publicly is gated on **G2** (counsel / legal review) +
**G3** (publisher opt-in), surfaced live via `getEconomics().publicPublishingAllowed`
(`ANTIEK_SPEAK_PUBLIC_PUBLISHING`). Disbursement — money actually leaving escrow —
is gated on **G2/G3** + `ANTIEK_STRIPE_PROVIDER=real`
(`getEconomics().disbursementAllowed`). The contributor split **accrues to
escrow now** (the 70% share is shown as attribution, "owed, not paid"); the
balance is honestly **$0.00 with no buyers and no ad revenue**, and is **never
disbursed pre-gate** — there is deliberately no disburse/pay control on any
surface, and the backend refuses disbursement (`contributor.py:356`)
(`SpeakSettings.tsx:160-264`).

### Operator env flips — the action list

A maintainer can open each gated capability from this list alone. These are
**operator-only env actions** (a deliberate flag flip post-precondition), never
a click in the UI:

- **`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`** — opens **G7**: open public participation
  (a stranger can contribute to a public remembrance). *Precondition:* the
  ecosystem / multi-user decision (single-operator until ~Sprint 22). When set,
  the `open-public` flip stops returning 403; the lane's G7 lock copy is the one
  surface that would still need a follow-up FE read to flip (it is static today —
  see Known gaps).
- **`ANTIEK_SPEAK_PUBLIC_PUBLISHING`** (with **G2** counsel + **G3** opt-in) —
  opens **public publishing**: a remembrance can be shared publicly. When set,
  `publicPublishingAllowed` reads true and the explainer + Settings flip to the
  honest "open" state copy live.
- **`ANTIEK_STRIPE_PROVIDER=real`** (with **G2** + **G3**) — opens
  **disbursement**: accrued escrow shares can route to contributors. When set,
  `disbursementAllowed` reads true and the payout copy flips to "money can now
  route" live.

### Known gaps (honest, NOT green-washed)

a. **33 pre-existing non-Speak full-suite test failures.** The integration
   branch carries 33 full-suite FE test failures that exist on `origin/main` and
   are **not introduced by this work** — they cluster in non-Speak surfaces
   (hotkeys / persistence / ai-actions / copyLint→Notebook / `index.tsx` /
   PenguinMascot). **The Speak surface itself is green** (the SPR-05 verify ran
   `Speak SpeakInvite gateHonesty PublicLane SpeakIndex SpeakSettings` → 7 files
   / 61 tests passed, 0 failed; `tsc -b --noEmit` → 0 errors). They are recorded
   here so the capstone does not imply a clean full tree.

b. **Backend / operator carry-forwards NOT built.** Two backend pieces remain so
   a stranger's "Add your memory" can work end-to-end once G7 opens (both raised
   in "Open questions for the operator" above, neither implemented):
   - an **unauthenticated read-only public browse route** (sibling to
     `/speak/invite/:token`) so a logged-out visitor can browse public
     remembrances; and
   - a **G7-gated token-mint endpoint** that hands an unauthenticated visitor a
     contribution token from a feed item.
   Until both ship, the public lane stays authed-only behind `RequireAuth`, and
   it is honest about that. (Also: the G7 lock panel is static copy with no FE
   read — when `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM` is set, that panel needs a small
   follow-up to read G7 live, the same way G2/G3 already do.)

c. **The per-second ad model stays rejected.** §9.3 Option-B
   (`claim_confidence × (6 − source_tier)`, escrow-only) is the basis; the
   per-second / timecode / mid-roll revenue model is a category error for a
   text/book deliverable (full argument in "Payout basis" above). The per-second
   grep over the Speak surface is empty.

### Capstone verification (SPR-05, recorded)

- **Voice / §5 sweep (M1):** every Speak surface read against §5 — **clean**, no
  slop/honesty defect found, no surface file touched. The slop scan
  (`powered by|seamless|leverage|…`) and the proven/true scan are both empty for
  rendered copy.
- **State-completeness (M2):** every surface × {empty, loading, error} has a
  designed state; AI/network calls fail into `AIActionFailure` or an honest
  inline message, never a swallowed error or raw spinner. Tests exercise the
  feed-failure (`PublicLane.test.tsx:212`) and draft-failure (`Speak.test.tsx:145`)
  paths.
- **Dark-mode + a11y (M3):** `dark:` parity present on every surface; tablist /
  `role="tab"` / `aria-selected` (`SpeakIndex/index.tsx:170-187`),
  `aria-expanded` Settings toggle, `role="note"` G7 panel, `role="alert"` +
  `aria-live` failure surface, and `aria-label` on the create / search / payout
  inputs — all confirmed at the cited lines.
- **e2e (M4):** `speak-biography.spec.ts` + `speak-private-journey.spec.ts`
  exist; each smoke-tests the real Speak stories that exist and marks the full
  live-server journey `test.skip` with a documented reason (Storybook has no
  live `/speak` server). Both lanes' journeys are represented. (`speak-publish.spec.ts`
  — not part of this spine's M4 set — carried THREE stale assertions (a "no project
  selected" guidance string, "biography projects", and a "create" button) from before
  the one-door redesign; the capstone FIXED all three by syncing them to the shipped
  one-door copy ("No one selected.", "Who do you want to remember?", "Start their
  story") rather than leave a known red.)
- **Tidy:** `*.tsbuildinfo` added to `apps/reading/.gitignore`; BOTH leaked
  build-cache files — `tsconfig.app.tsbuildinfo` AND `tsconfig.node.tsbuildinfo`
  (the latter a pre-existing SPR-10 leak of the same class) — removed from git
  tracking (`git rm --cached`) so neither is committed again.

---

## Change log

- **2026-06-04** — Capstone close (SPR-05 M6). Added "What shipped vs what's
  gated" — private-lane end-to-end, public-lane honest lock (G7 static / G2·G3
  live), escrow-only payout ($0, never disbursed pre-gate), the three operator
  env flips and their preconditions, and the honest known-gaps list (33
  pre-existing non-Speak failures, the two unbuilt backend carry-forwards, the
  rejected per-second model). Plus the M1–M4 capstone verification record and
  the tsbuildinfo tidy. No surface copy changed — the craft sweep found the
  Speak surface clean.
- **2026-06-04** — Initial ratification (SPR-01 M1 + M6). State map, dead-end
  defect, payout basis, gate phrasing, vocabulary, and ownership handoff
  recorded. No prior version.
