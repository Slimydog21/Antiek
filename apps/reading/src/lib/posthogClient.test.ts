/**
 * posthogClient.test.ts — the content firewall (master-spec §9.0).
 *
 * Antiek's reading/research content is substrate-owned and must never reach a
 * third party. Autocapture is ON for behavioural data, so the load-bearing
 * guarantee is `sanitizeOutgoingEvent`: every outgoing event is scrubbed of
 * URL query strings and of all three autocapture text channels (top-level
 * `$el_text`, the `$elements` array, and the flat `$elements_chain`) while the
 * person model (email, auth_method) and structural interaction data survive.
 *
 * These tests pin that contract. If autocapture or before_send is ever
 * loosened, a content channel reopens and one of these fails — the regression
 * is mechanical, not a matter of review vigilance.
 */
import { describe, expect, it } from "vitest";

import { sanitizeOutgoingEvent } from "./posthogClient";

// Minimal CaptureResult factory — only the fields the firewall touches.
function event(properties: Record<string, unknown>, extra = {}) {
  return {
    uuid: "00000000-0000-0000-0000-000000000000",
    event: "$autocapture",
    properties,
    ...extra,
  } as Parameters<typeof sanitizeOutgoingEvent>[0];
}

describe("sanitizeOutgoingEvent — content firewall", () => {
  it("passes a null event through untouched", () => {
    expect(sanitizeOutgoingEvent(null)).toBeNull();
  });

  it("strips query string and fragment from URL properties, keeps path", () => {
    const out = sanitizeOutgoingEvent(
      event({
        $current_url: "https://antiek.ai/research/abc-123?q=secret+query#frag",
        $referrer: "https://antiek.ai/read/doc-9?token=abc",
        $pathname: "/research/abc-123",
        $referring_domain: "antiek.ai",
      }),
    );
    const p = out!.properties;
    expect(p.$current_url).toBe("https://antiek.ai/research/abc-123");
    expect(p.$referrer).toBe("https://antiek.ai/read/doc-9");
    // path-only / host-only properties are not content and are preserved
    expect(p.$pathname).toBe("/research/abc-123");
    expect(p.$referring_domain).toBe("antiek.ai");
  });

  it("removes the top-level autocapture element text", () => {
    const out = sanitizeOutgoingEvent(
      event({ $el_text: "The title of a private document", $event_type: "click" }),
    );
    expect(out!.properties.$el_text).toBeUndefined();
    // non-content structural property survives
    expect(out!.properties.$event_type).toBe("click");
  });

  it("scrubs text/value from the $elements array but keeps structure", () => {
    const out = sanitizeOutgoingEvent(
      event({
        $elements: [
          {
            tag_name: "a",
            $el_text: "Confidential chapter heading",
            text: "Confidential chapter heading",
            attr__value: "secret-input-value",
            attr__class: "doc-link",
            nth_child: 3,
            href: "https://antiek.ai/read/doc-9?token=abc",
          },
        ],
      }),
    );
    const el = (out!.properties.$elements as Record<string, unknown>[])[0];
    expect(el.$el_text).toBeUndefined();
    expect(el.text).toBeUndefined();
    expect(el.attr__value).toBeUndefined();
    expect(el.href).toBe("https://antiek.ai/read/doc-9"); // query stripped
    // structural identity preserved so events still group
    expect(el.tag_name).toBe("a");
    expect(el.attr__class).toBe("doc-link");
    expect(el.nth_child).toBe(3);
  });

  it("strips text= and attr__value= from $elements_chain, keeps tags", () => {
    const out = sanitizeOutgoingEvent(
      event({
        $elements_chain:
          'a.doc-link:text="Confidential heading"attr__value="secret"nth-child="3"',
      }),
    );
    const chain = out!.properties.$elements_chain as string;
    expect(chain).not.toContain("Confidential heading");
    expect(chain).not.toContain("secret");
    // tag and structural attributes remain for grouping
    expect(chain).toContain("a.doc-link");
    expect(chain).toContain('nth-child="3"');
  });

  it("preserves the person model and scrubs $set/$set_once URLs", () => {
    const out = sanitizeOutgoingEvent(
      event(
        {},
        {
          $set: {
            email: "operator@antiek.ai",
            auth_method: "magic_link",
            $initial_current_url: "https://antiek.ai/?invite=secret",
          },
          $set_once: { first_seen_auth_method: "magic_link" },
        },
      ),
    );
    // identity survives — it is the point of identified analytics
    expect(out!.$set!.email).toBe("operator@antiek.ai");
    expect(out!.$set!.auth_method).toBe("magic_link");
    expect(out!.$set_once!.first_seen_auth_method).toBe("magic_link");
    // but a URL riding on person properties is still scrubbed
    expect(out!.$set!.$initial_current_url).toBe("https://antiek.ai/");
  });
});
