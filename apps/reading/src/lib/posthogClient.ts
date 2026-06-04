import posthog from "posthog-js";
import type { BeforeSendFn, CaptureResult, Properties, Property } from "posthog-js";

const projectToken = import.meta.env.VITE_POSTHOG_PROJECT_TOKEN?.trim();
const apiHost = import.meta.env.VITE_POSTHOG_HOST?.trim();

/** True when a project token is configured (analytics on). */
export const posthogEnabled = Boolean(projectToken);

/**
 * Strip the query string and fragment from a URL, keeping origin + path.
 * Path is structural (`/research/<uuid>`); query/hash can carry content
 * (e.g. a research query in `?q=`). Non-strings pass through untouched.
 */
function stripUrlContent(value: Property): Property {
  if (typeof value !== "string") return value;
  const cut = value.search(/[?#]/);
  return cut === -1 ? value : value.slice(0, cut);
}

// Event properties that can carry a full URL — and therefore query-string
// content. `$pathname` is path-only and `$referring_domain` is host-only, so
// neither needs scrubbing. The `$initial_*` pair rides on $set/$set_once.
const URL_PROPERTIES = [
  "$current_url",
  "$referrer",
  "$initial_current_url",
  "$initial_referrer",
];

/**
 * Defense-in-depth denylist of CUSTOM event-property keys that, by their name,
 * could carry substrate content (free text, document/research material).
 *
 * WHY THIS EXISTS (master-spec §9.0): substrate content must never leave the
 * browser. A taxonomy review of all 20 events in `analytics.ts` (2026-06-04)
 * confirmed NO event currently sends raw content — today every property is a
 * length, an id, a boolean, or an enum (`question_length`, `session_id`,
 * `has_passage`, `block_type`, …). This denylist is therefore not fixing a
 * live leak; it is a structural backstop so that if a future contributor adds
 * a content-bearing property to an event (e.g. `query`, `document_title`,
 * `passage_text`) it is stripped at the firewall even before the taxonomy or a
 * code review catches it.
 *
 * CONSEQUENCE OF REMOVING THIS: a future `track("...", { query: "<user text>" })`
 * would ship the user's research query / document content to a third party —
 * the exact §9.0 violation the firewall exists to prevent. Do not delete; add
 * to it when you add any custom property whose value could be free text.
 *
 * Matching is by exact key on custom (non-`$`-prefixed) properties plus a few
 * known content-bearing names; PostHog-internal `$`-prefixed keys are handled
 * by the URL / autocapture logic above and are intentionally NOT in this list.
 */
const CONTENT_PROPERTY_DENYLIST = new Set<string>([
  "query",
  "search_query",
  "question",
  "question_text",
  "problem",
  "problem_text",
  "prompt",
  "passage",
  "passage_text",
  "selection",
  "selected_text",
  "title",
  "document_title",
  "doc_title",
  "name",
  "text",
  "body",
  "content",
  "note",
  "answer",
  "message",
  "transcript",
  "summary",
  "excerpt",
  "snippet",
]);

/**
 * Structural `attr__*` allowlist. PostHog autocapture serializes EVERY DOM
 * attribute on a captured element as `attr__<name>` (each ≤1024 chars),
 * excluding only name/id/class/aria-label from its own generic capture — which
 * means content-bearing attributes (`attr__title`, `attr__alt`,
 * `attr__placeholder`, `attr__data-*`, …) DO get serialized and would egress
 * substrate content through both the `$elements[]` array and the
 * `$elements_chain` string. We therefore DROP every `attr__*` key except this
 * small structural allowlist:
 *   - `attr__class` / `attr__id` — pure structural identity (no content), used
 *     for event grouping / funnels.
 *   - `href` / `attr__href` — kept but URL-scrubbed elsewhere (query strings
 *     redacted), because the path is structural even though the query is not.
 * Everything else under `attr__*` is treated as potential content and removed.
 */
const STRUCTURAL_ATTR_ALLOWLIST = new Set<string>([
  "attr__class",
  "attr__id",
  "attr__href",
  "href",
]);

/**
 * Mutate one property bag in place: redact URL query strings and remove every
 * autocapture text channel. Autocapture serializes the clicked DOM subtree
 * into (a) a top-level `$el_text`, (b) an `$elements`/`elements` array whose
 * entries carry `$el_text`/`text`/`attr__value` AND an arbitrary set of
 * `attr__<name>` DOM attributes, and (c) a flat `$elements_chain` string. On a
 * reading surface all of these can contain document content, so we strip text
 * + input values + every non-structural `attr__*` while preserving structural
 * identity (tag / classes / id / position) so events still group.
 */
function scrubProperties(props: Properties | undefined): void {
  // Guard against non-object property bags. posthog-js types `properties` as
  // `Properties`, but a malformed event (or a future SDK shape) could carry a
  // null, an array, or a primitive here. We only mutate plain objects; anything
  // else is left as-is so we never throw (a throw drops the event — see
  // sanitizeOutgoingEvent's contract below).
  if (!props || typeof props !== "object" || Array.isArray(props)) return;

  for (const key of URL_PROPERTIES) {
    if (key in props) props[key] = stripUrlContent(props[key]);
  }

  // (a) top-level clicked-element text
  delete props.$el_text;

  // (b) serialized element array
  const elements = props.$elements ?? props.elements;
  if (Array.isArray(elements)) {
    for (const raw of elements) {
      if (!raw || typeof raw !== "object") continue;
      const el = raw as Record<string, unknown>;
      delete el.$el_text;
      delete el.text;
      // Drop every `attr__*` DOM-attribute key (incl. attr__value, attr__title,
      // attr__alt, attr__placeholder, attr__data-*, …) UNLESS it is in the
      // structural allowlist. posthog serializes arbitrary DOM attributes, so a
      // name-by-name denylist would always lag a content-bearing attribute; an
      // allowlist fails closed.
      for (const elKey of Object.keys(el)) {
        if (elKey.startsWith("attr__") && !STRUCTURAL_ATTR_ALLOWLIST.has(elKey)) {
          delete el[elKey];
        }
      }
      // Both the parsed `href` and PostHog's raw `attr__href` carry the full
      // URL — query strings on either can hold content (e.g. ?token / ?q), so
      // scrub both, keeping origin+path for grouping.
      if (typeof el.href === "string") el.href = stripUrlContent(el.href);
      if (typeof el.attr__href === "string")
        el.attr__href = stripUrlContent(el.attr__href);
    }
  }

  // (c) flattened element chain — posthog flattens the same channels as the
  // array into one string (`tag.class:text="…"attr__title="…"href="…"nth-child="…";…`).
  // We must scrub the SAME surface the array scrub covers, boundary-aware so we
  // don't mangle structure:
  //   - the bare `text="…"` channel (autocapture el text)
  //   - EVERY `attr__<name>="…"` whose <name> is not in the structural
  //     allowlist (so attr__value/attr__title/attr__alt/attr__placeholder/… go,
  //     while attr__class/attr__id stay) — matched only at a real attribute
  //     boundary (start, or after `:`/`;`/`"`) so `attr__text="…"` is treated as
  //     the attr__ channel, NOT as the bare `text=` channel (DEFECT 3).
  //   - `href`/`attr__href` URL query strings (kept but redacted).
  if (typeof props.$elements_chain === "string") {
    props.$elements_chain = props.$elements_chain
      // attr__<name>="…": drop the value for any non-allowlisted name, anchored
      // at an attribute boundary via a ZERO-WIDTH lookbehind so the delimiter is
      // not consumed (adjacent `attr__a="…"attr__b="…"` pairs both match).
      // href/attr__href are excluded here and handled by the URL-redaction pass
      // below (allowlisted → kept, query stripped).
      .replace(
        // value body `(?:\\.|[^"\\])*` spans PostHog's escaped quotes (it
        // escapes inner `"` as `\"` when building the chain) so content after
        // a quote inside a value cannot ride out — a plain `[^"]*` would stop
        // at the first `\"` and leak the rest (§9.0).
        /(?<=^|[:;"])(attr__[A-Za-z0-9_-]+)="(?:\\.|[^"\\])*"/g,
        (m, attr: string) =>
          STRUCTURAL_ATTR_ALLOWLIST.has(attr) ? m : `${attr}=""`,
      )
      // bare text="…" channel, anchored at a boundary so attr__text (already
      // handled above) and other *text suffixes are not collateral.
      .replace(/(?<=^|[:;"])text="(?:\\.|[^"\\])*"/g, () => `text=""`)
      // href / attr__href: keep the structural path, strip the query/fragment.
      .replace(
        /((?:attr__)?href=")((?:\\.|[^"\\])*)(")/g,
        (_m, pre: string, url: string, post: string) => {
          const cut = url.search(/[?#]/);
          return pre + (cut === -1 ? url : url.slice(0, cut)) + post;
        },
      );
  }

  // (d) custom content-property denylist (§9.0 defense-in-depth — see
  // CONTENT_PROPERTY_DENYLIST). Strip any custom key whose name implies it
  // could hold substrate free text. `$`-prefixed PostHog-internal keys are
  // never denylisted (URL/autocapture handling above owns them, and structural
  // props like `$event_type` must survive).
  for (const key of Object.keys(props)) {
    if (key.startsWith("$")) continue;
    if (CONTENT_PROPERTY_DENYLIST.has(key)) delete props[key];
  }
}

/**
 * Content firewall (master-spec §9.0 + substrate-as-source-of-truth).
 *
 * §9.0 posture (autocapture-ON-but-scrubbed, fail-closed, recording-off, the
 * deferred $elements_chain skeletonize follow-up): see
 * docs/decisions/posthog-content-firewall.md
 *
 * Antiek's reading/research content is substrate-owned and must never reach a
 * third party. Autocapture stays ON for rich behavioural data, but every
 * outgoing event — its own properties and any person-property $set/$set_once —
 * is scrubbed of URL query strings and element text before it leaves the
 * browser. Identity properties (email, auth_method) are not URLs or element
 * text, so they survive: we lose content, never the person model.
 *
 * NEVER-NULLISH / NEVER-THROW CONTRACT (highest-stakes invariant):
 * posthog-js's before_send runner treats a `null` OR `undefined` return as
 * "event rejected" and DROPS the event, and a throw aborts capture before the
 * event is sent. Confirmed in posthog-js@1.379.1, dist/main.js:
 *   - `Wt=t=>void 0===t`, `Jt=t=>null===t`, `Kt=t=>Wt(t)||Jt(t)` (isNullish)
 *   - runner `vn(t)`: `for (r of fns) { if (i=r(i), Kt(i)) { ...; return null } }`
 *   - call site: `var E=this.vn(p); if(!E) return; p=E` — any falsy return
 *     aborts capture (no `eventCaptured`, no `/e/` POST).
 * Both failure modes are an availability problem (a dropped/halted event).
 * §9.0 — substrate content must never egress — is a HARD invariant, while
 * "never drop an event" is an availability PREFERENCE. The two are jointly
 * satisfiable, so we honour both: this function MUST always return the SAME
 * event object for any non-null input (never nullish, never throw → never a
 * drop), AND it must FAIL CLOSED on content (never return an event whose
 * content bags survived a scrub failure).
 *
 * FAIL-CLOSED CONTRACT (§9.0 dominates availability):
 * Each content bag is scrubbed under its OWN try/catch, so a throw scrubbing
 * one bag never leaves the others unscrubbed. If a bag's scrub throws (a
 * pathological shape — frozen object, getter that throws, exotic prototype),
 * we do NOT preserve that bag's raw content; we NEUTRALIZE it
 * (`properties → {}`, `$set/$set_once → undefined`) and keep going. The event
 * still flows (availability preserved) but carries no content from a bag we
 * could not prove clean (§9.0 preserved). Returning the raw, un-scrubbed event
 * on a throw — the prior behaviour — INVERTS the priority for a §9.0 surface:
 * it trades a guaranteed content leak for an availability nicety. Never do
 * that here.
 *
 * CONSEQUENCE OF REVERTING TO FAIL-OPEN: a single event shape that makes a
 * scrub throw would egress whatever content lived in that bag (document text,
 * a research query, a tooltip/caption) to a third party — the exact §9.0
 * violation this firewall exists to prevent.
 */
export const sanitizeOutgoingEvent: BeforeSendFn = (
  event: CaptureResult | null,
) => {
  if (!event) return event;
  // Per-bag fail-closed: scrub each content bag in isolation; on ANY throw,
  // neutralize THAT bag (drop its content) rather than letting raw content
  // egress. Other bags are unaffected.
  try {
    scrubProperties(event.properties);
  } catch {
    event.properties = {};
  }
  try {
    scrubProperties(event.$set);
  } catch {
    event.$set = undefined;
  }
  try {
    scrubProperties(event.$set_once);
  } catch {
    event.$set_once = undefined;
  }
  return event;
};

if (posthogEnabled) {
  posthog.init(projectToken!, {
    api_host: apiHost || "https://eu.i.posthog.com",
    // Capture config is set EXPLICITLY, not via a dated `defaults` bundle.
    // A future-dated `defaults: "2026-01-30"` (the SDK has no defaults set for
    // a future date) left prod initialized but capturing ZERO events — remote
    // config + flags + surveys loaded, yet no `/e/` egress on initial load,
    // SPA navigation, or click (confirmed against the live bundle and the
    // PostHog events API, no JS errors / opt-out / quota). Explicit flags make
    // capture behaviour fully determined here and verifiable.
    capture_pageview: true, // initial load + SPA route changes
    capture_pageleave: true,
    autocapture: true, // behavioural data; element text scrubbed by before_send
    person_profiles: "identified_only",
    // Session recording pinned OFF in code — replay records on-screen reading
    // content; never enable without full input/text masking. The before_send
    // firewall scrubs URL query strings + autocapture element text from every
    // event regardless of feature — see sanitizeOutgoingEvent.
    disable_session_recording: true,
    before_send: sanitizeOutgoingEvent,
  });
}

export { posthog };
