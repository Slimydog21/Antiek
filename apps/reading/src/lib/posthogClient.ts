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
 * Mutate one property bag in place: redact URL query strings and remove every
 * autocapture text channel. Autocapture serializes the clicked DOM subtree
 * into (a) a top-level `$el_text`, (b) an `$elements`/`elements` array whose
 * entries carry `$el_text`/`text`/`attr__value`, and (c) a flat
 * `$elements_chain` string. On a reading surface all three can contain
 * document content, so we strip text + input values while preserving
 * structural identity (tag / classes / id / position) so events still group.
 */
function scrubProperties(props: Properties | undefined): void {
  if (!props) return;

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
      delete el.attr__value;
      if (typeof el.href === "string") el.href = stripUrlContent(el.href);
    }
  }

  // (c) flattened element chain — drop text/value attributes only, keep tags
  if (typeof props.$elements_chain === "string") {
    props.$elements_chain = props.$elements_chain
      .replace(/text="[^"]*"/g, "")
      .replace(/attr__value="[^"]*"/g, "");
  }
}

/**
 * Content firewall (master-spec §9.0 + substrate-as-source-of-truth).
 *
 * Antiek's reading/research content is substrate-owned and must never reach a
 * third party. Autocapture stays ON for rich behavioural data, but every
 * outgoing event — its own properties and any person-property $set/$set_once —
 * is scrubbed of URL query strings and element text before it leaves the
 * browser. Identity properties (email, auth_method) are not URLs or element
 * text, so they survive: we lose content, never the person model.
 */
export const sanitizeOutgoingEvent: BeforeSendFn = (
  event: CaptureResult | null,
) => {
  if (!event) return event;
  scrubProperties(event.properties);
  scrubProperties(event.$set);
  scrubProperties(event.$set_once);
  return event;
};

if (posthogEnabled) {
  posthog.init(projectToken!, {
    api_host: apiHost || "https://eu.i.posthog.com",
    defaults: "2026-01-30",
    person_profiles: "identified_only",
    // Capture richly, never leak content. Autocapture ON (behavioural data);
    // route-change pageviews stay on (opaque UUID paths). Session recording is
    // pinned OFF in code — replay records the on-screen reading content, so it
    // must not be silently enabled from the project dashboard; re-enable only
    // with full input/text masking. The before_send firewall scrubs content
    // from every event regardless of feature — see sanitizeOutgoingEvent.
    autocapture: true,
    disable_session_recording: true,
    before_send: sanitizeOutgoingEvent,
  });
}

export { posthog };
