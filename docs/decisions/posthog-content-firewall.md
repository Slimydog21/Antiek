# PostHog content firewall — autocapture ON but scrubbed at `before_send`

**Decision date:** 2026-06-04
**Status:** ✅ Active (shipped in `apps/reading/src/lib/posthogClient.ts`; enforced by `posthogClient.test.ts`)
**Owner:** operator + reading-app analytics (PostHog Analytics Hardening, SPR-04 firewall)

## The decision

PostHog autocapture stays **ON** for the reading/research surface, but every
outgoing event is scrubbed of substrate content by a `before_send` hook
(`sanitizeOutgoingEvent` in `apps/reading/src/lib/posthogClient.ts`) **before**
it leaves the browser. The alternative — disabling autocapture to be "safe" —
was rejected: it would have thrown away rich behavioural data AND, worse, hidden
the leaks instead of closing them (see the SPR-04 chain-leak finding below).

This is the master-spec **§9.0** posture made concrete on the analytics surface:
substrate content (document text, research queries, passages, free text) must
never reach a third party; behavioural shape (which element, which route, the
person model) may.

## What is scrubbed (the firewall surface)

`sanitizeOutgoingEvent` runs `scrubProperties` over the event's `properties`,
`$set`, and `$set_once` bags. `scrubProperties` closes every channel through
which autocapture can serialize page/DOM content:

- **URL query strings + fragments** — `stripUrlContent` keeps `origin + path`
  (path is structural, e.g. `/research/<uuid>`) and drops `?…`/`#…` (a query can
  carry a research query in `?q=`). Applied to `$current_url`, `$referrer`,
  `$initial_current_url`, `$initial_referrer`. `$pathname` (path-only) and
  `$referring_domain` (host-only) need no scrubbing.
- **Top-level clicked-element text** — `delete props.$el_text`.
- **The serialized `$elements`/`elements` array** — for each entry, delete
  `$el_text` and `text`, scrub `href`/`attr__href` query strings, and drop every
  `attr__*` DOM-attribute key NOT in the structural allowlist.
- **The flattened `$elements_chain` string** — posthog flattens the same channels
  into one string (`tag.class:text="…"attr__value="…"attr__title="…"href="…";…`,
  where `attr__value` is a captured input's value and `attr__title`/`attr__alt`/
  `attr__data-*` are arbitrary DOM attributes — all content-bearing). The scrub is
  boundary-aware (anchored at `^`/`:`/`;`/`"`): it drops the bare `text="…"`
  channel, blanks every non-allowlisted `attr__<name>="…"` value, and strips
  href query strings — with a value-body matcher (`(?:\\.|[^"\\])*`) that spans
  posthog's escaped inner quotes so content after a `\"` cannot ride out.
- **A custom content-property denylist** (`CONTENT_PROPERTY_DENYLIST`) — defense
  in depth: any custom (non-`$`) property whose NAME implies free text (`query`,
  `passage_text`, `document_title`, `note`, `transcript`, …) is deleted, so a
  future `track("…", { query: "<user text>" })` is stripped at the firewall even
  before a code review or the SPR-01 taxonomy gate catches it.

### The `attr__*` structural allowlist

PostHog autocapture serializes **every** DOM attribute on a captured element as
`attr__<name>`, so a name-by-name denylist would always lag a content-bearing
attribute. We therefore **DROP every `attr__*` key except an allowlist** —
`STRUCTURAL_ATTR_ALLOWLIST = { attr__class, attr__id, attr__href, href }` — which
fails closed: an attribute we did not anticipate is dropped, not leaked.
`href`/`attr__href` are kept but URL-scrubbed (path structural, query not).

## identified_only, session-recording OFF

- **`person_profiles: "identified_only"`** — no anonymous person profiles; the
  person model is created only for an identified (signed-in) user. The identify
  call lives in `apps/reading/src/lib/auth.tsx` (`posthog.identify(user_id, …)`,
  `posthog.reset()` on sign-out); `distinct_id` is the substrate `user_id`, never
  PII. `email`/`auth_method` are deliberate person properties on a
  GDPR-resident, identified_only project — they are not URLs or element text, so
  the firewall preserves them: we lose content, never the person model.
- **`disable_session_recording: true`** — pinned OFF in code. Replay would record
  on-screen reading content verbatim; never enable without full input/text
  masking, and even then only behind an explicit §9.0 review.

## The fail-CLOSED / never-undefined guard (highest-stakes invariant)

posthog-js's `before_send` runner treats a `null` OR `undefined` return as
"event rejected" (DROP), and a throw aborts capture entirely (confirmed in
posthog-js@1.379.1, `dist/main.js` — `isNullish` + the `vn` runner + the
`if(!E) return` call site). So:

- **Never-nullish / never-throw** — `sanitizeOutgoingEvent` always returns the
  SAME event object for any non-null input. Dropping events is an *availability*
  problem; §9.0 is a *hard* invariant; the two are jointly satisfiable, so we
  honour both.
- **Fail CLOSED, per bag** — each content bag is scrubbed under its OWN
  `try/catch`. If a bag's scrub throws (pathological shape — frozen object,
  throwing getter, exotic prototype), we do NOT preserve that bag's raw content;
  we **NEUTRALIZE** it (`properties → {}`, `$set`/`$set_once → undefined`) and
  keep going. The event still flows (availability) but carries no content from a
  bag we could not prove clean (§9.0). Returning the raw, un-scrubbed event on a
  throw — fail-OPEN — would trade a guaranteed content leak for an availability
  nicety on a §9.0 surface. Never do that here.

## Known follow-up — the `$elements_chain` scrub is grammar-coupled

The `$elements_chain` scrub (channel (c) above) is a set of regexes against
PostHog's flattened-chain GRAMMAR. That grammar is an internal serialization
detail, not a stable contract: across SPR-04's review rounds, **three separate
rounds each found a deeper chain leak** (a `text=` vs `attr__text` boundary
confusion, an escaped-quote value body that stopped at the first `\"`, and the
`attr__href` raw key). Each was closed, but the scrub remains coupled to a
grammar PostHog can change without notice.

The robust follow-up (deferred, not yet shipped) is to stop *parsing* the chain
and instead **drop or skeletonize `$elements_chain` entirely** — keep only a
structural skeleton (tags + allowlisted attrs) reconstructed from the already-
scrubbed `$elements[]` array, or delete the chain and let the array be the single
source. That removes the grammar dependency at the cost of the chain's
convenience. Tracked as a deferral; the array scrub is the load-bearing one.

## Reconsider if

- **Reconsider dropping/skeletonizing `$elements_chain`** the next time a posthog
  upgrade changes the chain grammar OR a fourth chain leak is found by review —
  at that point the grammar-coupled regex scrub has earned its replacement; stop
  parsing the chain and reconstruct a structural skeleton from `$elements[]`.
- **Reconsider the allowlist (not a denylist) for `attr__*`** only if a needed
  structural attribute is being dropped — add it to `STRUCTURAL_ATTR_ALLOWLIST`
  with a one-line note; never invert to a denylist (a denylist fails open against
  a content-bearing attribute posthog adds).
- **Reconsider enabling session recording** only behind full input/text masking
  AND an explicit §9.0 review; the default OFF is load-bearing, not incidental.
- **Reconsider the fail-CLOSED neutralize** only if §9.0 ceases to dominate
  availability on this surface — which it does not while reading content is
  substrate-owned. If a future surface is content-free, a fail-open scrub could
  be argued there, but never here.

## Defensibility

The exact channels, the allowlist contents, the never-nullish/never-throw
contract, and the fail-closed neutralize are recorded here AND restated as
load-bearing comments in `apps/reading/src/lib/posthogClient.ts`, with
`posthogClient.test.ts` pinning the behaviour (including the three chain leaks
SPR-04 closed). A future maintainer can re-derive why autocapture is ON-but-
scrubbed rather than OFF, and why a scrub throw neutralizes rather than passes
through.
