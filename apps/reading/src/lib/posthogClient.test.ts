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

// ---------------------------------------------------------------------------
// SPR-04 — M1: never-nullish / never-throw guarantee.
//
// posthog-js@1.379.1 drops any event whose before_send returns null OR
// undefined, and aborts capture if before_send throws. Verified in
// node_modules/posthog-js/dist/main.js:
//   Wt=t=>void 0===t ; Jt=t=>null===t ; Kt=t=>Wt(t)||Jt(t)  (isNullish)
//   runner vn(t): for(r of fns){ if(i=r(i), Kt(i)){ ...; return null } }
//   call site:    var E=this.vn(p); if(!E) return; p=E   (falsy return => no send)
// A drop is a SILENT analytics outage — the worst failure for this firewall.
// This battery asserts: for every non-null input we get back the SAME event
// reference (never undefined, never null-from-our-fn) and never throw.
// ---------------------------------------------------------------------------
describe("sanitizeOutgoingEvent — never drops an event (M1)", () => {
  // Build deliberately malformed / hostile shapes. We bypass the `event()`
  // factory's typing on purpose to feed shapes the type system forbids but the
  // runtime could still see (a different SDK build, a corrupted event).
  const make = (props: unknown, extra: Record<string, unknown> = {}) =>
    ({
      uuid: "00000000-0000-0000-0000-000000000000",
      event: "$autocapture",
      properties: props,
      ...extra,
    }) as Parameters<typeof sanitizeOutgoingEvent>[0];

  const frozenProps = Object.freeze({
    $el_text: "frozen secret",
    $current_url: "https://antiek.ai/x?q=frozen",
  });

  const battery: Array<[string, Parameters<typeof sanitizeOutgoingEvent>[0]]> = [
    ["empty properties", make({})],
    ["missing properties (undefined)", make(undefined)],
    ["null properties", make(null)],
    ["properties is an array", make([1, 2, 3])],
    ["properties is a primitive string", make("not-an-object")],
    ["properties is a number", make(42)],
    ["missing $set / $set_once", make({ a: 1 })],
    ["$set is null", make({}, { $set: null })],
    ["$set is an array", make({}, { $set: [1, 2] })],
    ["$set_once is a primitive", make({}, { $set_once: "nope" })],
    [
      "$elements is not an array",
      make({ $elements: { tag_name: "a", text: "x" } }),
    ],
    [
      "$elements array with null / primitive entries",
      make({ $elements: [null, 7, "str", { text: "deep secret" }] }),
    ],
    [
      "non-string URL values",
      make({ $current_url: 12345, $referrer: { weird: true } }),
    ],
    [
      "non-string $elements_chain",
      make({ $elements_chain: { not: "a string" } }),
    ],
    ["frozen properties object", make(frozenProps)],
    [
      "frozen $set object",
      make({}, { $set: Object.freeze({ email: "a@b.c", $initial_referrer: "https://x/?q=1" }) }),
    ],
    [
      "property whose getter throws",
      make(
        Object.defineProperty({}, "$current_url", {
          enumerable: true,
          get() {
            throw new Error("hostile getter");
          },
        }),
      ),
    ],
    ["event with no properties key at all", { uuid: "u", event: "x" } as Parameters<typeof sanitizeOutgoingEvent>[0]],
  ];

  it.each(battery)(
    "returns the SAME event reference and never throws: %s",
    (_label, input) => {
      let out: ReturnType<typeof sanitizeOutgoingEvent> | undefined;
      expect(() => {
        out = sanitizeOutgoingEvent(input);
      }).not.toThrow();
      // never undefined, never (our-fn-introduced) null for a non-null input
      expect(out).not.toBeUndefined();
      expect(out).not.toBeNull();
      // same object reference — we mutate, never replace
      expect(out).toBe(input);
    },
  );

  it("returns null unchanged for a null event (the one allowed nullish path)", () => {
    // posthog only calls before_send with a real event, but the type allows
    // null; passing it through is correct — there is nothing to send anyway.
    expect(sanitizeOutgoingEvent(null)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// SPR-04 — M2: real prod event-shape fixtures, adversarial sentinel sweep.
//
// Intellectual honesty (rigor #1): instead of asserting "the field I
// remembered is gone", we plant a UNIQUE sentinel in EVERY content-bearing
// position, run the firewall, JSON.stringify the WHOLE returned event, and
// assert the sentinel appears NOWHERE. If a content channel exists that we
// forgot, this fails — exactly as it should.
// ---------------------------------------------------------------------------
describe("sanitizeOutgoingEvent — real prod shapes, sentinel never leaks (M2)", () => {
  const SENTINEL = "ZZQ_SENTINEL_8f3a1c_LEAK_CANARY";

  it("$pageview: content in ?q= does not survive anywhere in the event", () => {
    // Real posthog $pageview shape (subset of what the SDK emits).
    const pageview = {
      uuid: "01890000-0000-7000-8000-000000000001",
      event: "$pageview",
      properties: {
        $current_url: `https://antiek.ai/research/abc-123?q=${SENTINEL}&page=2#${SENTINEL}`,
        $referrer: `https://antiek.ai/read/doc-9?token=${SENTINEL}`,
        $initial_current_url: `https://antiek.ai/?invite=${SENTINEL}`,
        $pathname: "/research/abc-123",
        $referring_domain: "antiek.ai",
        $host: "antiek.ai",
        $browser: "Chrome",
        $screen_height: 1080,
      },
    } as Parameters<typeof sanitizeOutgoingEvent>[0];

    const out = sanitizeOutgoingEvent(pageview)!;
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    // structural URL parts preserved (path/host), so events still group
    expect(out.properties.$current_url).toBe(
      "https://antiek.ai/research/abc-123",
    );
    expect(out.properties.$pathname).toBe("/research/abc-123");
    expect(out.properties.$referring_domain).toBe("antiek.ai");
  });

  it("$autocapture: content in $el_text, $elements[], and $elements_chain does not survive", () => {
    // Real posthog $autocapture shape: all three text channels populated, the
    // way posthog's element serializer actually emits them.
    const autocapture = {
      uuid: "01890000-0000-7000-8000-000000000002",
      event: "$autocapture",
      properties: {
        $event_type: "click",
        $el_text: SENTINEL,
        $elements: [
          {
            tag_name: "a",
            $el_text: SENTINEL,
            text: SENTINEL,
            attr__value: SENTINEL,
            attr__href: `https://antiek.ai/read/doc-9?token=${SENTINEL}`,
            href: `https://antiek.ai/read/doc-9?token=${SENTINEL}`,
            attr__class: "doc-link",
            nth_child: 3,
            nth_of_type: 1,
          },
          {
            tag_name: "div",
            attr__class: "reader-pane",
            nth_child: 1,
          },
        ],
        $elements_chain: `a.doc-link:text="${SENTINEL}"attr__value="${SENTINEL}"href="https://antiek.ai/read/doc-9?token=${SENTINEL}"nth-child="3";div.reader-pane:nth-child="1"`,
        $current_url: `https://antiek.ai/read/doc-9?highlight=${SENTINEL}`,
      },
    } as Parameters<typeof sanitizeOutgoingEvent>[0];

    const out = sanitizeOutgoingEvent(autocapture)!;
    // THE adversarial assertion: nothing, anywhere, in the serialized event.
    expect(JSON.stringify(out)).not.toContain(SENTINEL);

    // and the structural skeleton survives so events still group/funnel
    const el0 = (out.properties.$elements as Record<string, unknown>[])[0];
    expect(el0.tag_name).toBe("a");
    expect(el0.attr__class).toBe("doc-link");
    expect(el0.nth_child).toBe(3);
    expect(out.properties.$event_type).toBe("click");
    expect(out.properties.$elements_chain as string).toContain("a.doc-link");
    expect(out.properties.$elements_chain as string).toContain('nth-child="3"');
  });

  it("$identify: $set.email + auth_method ARE preserved (identity is not content)", () => {
    const identify = {
      uuid: "01890000-0000-7000-8000-000000000003",
      event: "$identify",
      properties: {
        distinct_id: "user-7",
        $anon_distinct_id: "anon-7",
      },
      $set: {
        email: "operator@antiek.ai",
        auth_method: "magic_link",
        // a content-bearing URL riding on the person profile must still go
        $initial_current_url: `https://antiek.ai/?signup_q=${SENTINEL}`,
        $initial_referrer: `https://ref.example/?r=${SENTINEL}`,
      },
      $set_once: {
        first_seen_auth_method: "magic_link",
      },
    } as Parameters<typeof sanitizeOutgoingEvent>[0];

    const out = sanitizeOutgoingEvent(identify)!;
    // sentinel (planted in the $initial_* URLs) must be gone everywhere
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    // but identity is explicitly preserved — this is the point of $identify
    expect(out.$set!.email).toBe("operator@antiek.ai");
    expect(out.$set!.auth_method).toBe("magic_link");
    expect(out.$set_once!.first_seen_auth_method).toBe("magic_link");
    expect(out.$set!.$initial_current_url).toBe("https://antiek.ai/");
  });
});

// ---------------------------------------------------------------------------
// SPR-04 (sharpen r2) — D1: FAIL-CLOSED on a scrub throw.
//
// §9.0 (content never egresses) is a hard invariant; "never drop an event" is
// an availability preference. Both are satisfiable: on a scrub throw the event
// still flows, but the content bag that could not be proven clean is
// NEUTRALIZED, not returned raw. The prior round-1 catch returned the
// un-scrubbed event — green on a no-throw assertion while leaking the sentinel.
// These tests plant a sentinel behind a throwing getter and assert it appears
// NOWHERE in the returned event.
// ---------------------------------------------------------------------------
describe("sanitizeOutgoingEvent — fail closed on scrub throw (D1)", () => {
  const SENTINEL = "ZZQ_SENTINEL_throw_d1_LEAK_CANARY";

  // A property bag whose first URL-property read throws, but which ALSO carries
  // the sentinel in an enumerable own property. Round-1 would catch the throw
  // and return this bag intact → sentinel leaks. Fail-closed neutralizes it.
  function throwingPropsWithSentinel() {
    const bag: Record<string, unknown> = {
      leaked_field: SENTINEL,
      $el_text: SENTINEL,
    };
    Object.defineProperty(bag, "$current_url", {
      enumerable: true,
      configurable: true,
      get() {
        throw new Error("hostile getter carrying " + SENTINEL);
      },
    });
    return bag;
  }

  const make = (props: unknown, extra: Record<string, unknown> = {}) =>
    ({
      uuid: "00000000-0000-0000-0000-000000000000",
      event: "$autocapture",
      properties: props,
      ...extra,
    }) as Parameters<typeof sanitizeOutgoingEvent>[0];

  it("getter-throws in properties: sentinel does NOT survive (bag neutralized)", () => {
    const input = make(throwingPropsWithSentinel());
    let out: ReturnType<typeof sanitizeOutgoingEvent> | undefined;
    expect(() => {
      out = sanitizeOutgoingEvent(input);
    }).not.toThrow();
    // event still flows (availability preserved) and is the same reference
    expect(out).toBe(input);
    expect(out).not.toBeNull();
    // §9.0: the planted content is gone EVERYWHERE in the returned event
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    // the throwing bag was neutralized to an empty object
    expect(out!.properties).toEqual({});
  });

  it("getter-throws in $set: $set neutralized, sentinel gone, other bags intact", () => {
    const input = make(
      { question_length: 5 }, // clean properties bag must survive untouched
      { $set: throwingPropsWithSentinel() },
    );
    let out: ReturnType<typeof sanitizeOutgoingEvent> | undefined;
    expect(() => {
      out = sanitizeOutgoingEvent(input);
    }).not.toThrow();
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    // the throwing bag is dropped...
    expect(out!.$set).toBeUndefined();
    // ...but the independent, clean bag is preserved (per-bag isolation)
    expect(out!.properties.question_length).toBe(5);
  });

  it("getter-throws in $set_once: that bag neutralized, sentinel gone", () => {
    const input = make({}, { $set_once: throwingPropsWithSentinel() });
    let out: ReturnType<typeof sanitizeOutgoingEvent> | undefined;
    expect(() => {
      out = sanitizeOutgoingEvent(input);
    }).not.toThrow();
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    expect(out!.$set_once).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// SPR-04 (sharpen r2) — D2/D3: scrub ALL content-bearing attr__* (array+chain),
// boundary-aware so structure is not mangled.
//
// posthog autocapture serializes EVERY DOM attribute as attr__<name> (≤1024
// chars), excluding only name/id/class/aria-label from generic capture. So
// attr__title / attr__alt / attr__placeholder / attr__data-* carry content
// through BOTH the $elements[] array and the $elements_chain string. We keep a
// small structural allowlist (attr__class, attr__id, href/attr__href) and drop
// the rest. Sentinel planted in every such channel must not survive.
// ---------------------------------------------------------------------------
describe("sanitizeOutgoingEvent — non-structural attr__* never leak (D2/D3)", () => {
  const SENTINEL = "ZZQ_SENTINEL_attr_d2_LEAK_CANARY";

  it("$elements[]: attr__title/alt/placeholder/data-* are dropped, allowlist kept", () => {
    const out = sanitizeOutgoingEvent(
      event({
        $elements: [
          {
            tag_name: "img",
            attr__title: SENTINEL,
            attr__alt: SENTINEL,
            attr__placeholder: SENTINEL,
            "attr__data-note": SENTINEL,
            attr__value: SENTINEL,
            // structural allowlist — must survive
            attr__class: "doc-thumb",
            attr__id: "thumb-9",
            attr__href: `https://antiek.ai/read/doc-9?token=${SENTINEL}`,
            nth_child: 2,
          },
        ],
      }),
    )!;
    // nothing anywhere in the serialized event
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    const el = (out.properties.$elements as Record<string, unknown>[])[0];
    // non-structural attrs gone
    expect(el.attr__title).toBeUndefined();
    expect(el.attr__alt).toBeUndefined();
    expect(el.attr__placeholder).toBeUndefined();
    expect(el["attr__data-note"]).toBeUndefined();
    expect(el.attr__value).toBeUndefined();
    // structural identity preserved for grouping
    expect(el.tag_name).toBe("img");
    expect(el.attr__class).toBe("doc-thumb");
    expect(el.attr__id).toBe("thumb-9");
    expect(el.nth_child).toBe(2);
    // href kept but URL-scrubbed
    expect(el.attr__href).toBe("https://antiek.ai/read/doc-9");
  });

  it("$elements_chain: attr__title/alt/placeholder values scrubbed, structure kept", () => {
    const out = sanitizeOutgoingEvent(
      event({
        $elements_chain:
          `img.doc-thumb:attr__title="${SENTINEL}"attr__alt="${SENTINEL}"` +
          `attr__placeholder="${SENTINEL}"attr__class="doc-thumb"` +
          `attr__id="thumb-9"nth-child="2";div.reader-pane:nth-child="1"`,
      }),
    )!;
    const chain = out.properties.$elements_chain as string;
    // sentinel gone everywhere
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    expect(chain).not.toContain(SENTINEL);
    // structural attrs preserved
    expect(chain).toContain("img.doc-thumb");
    expect(chain).toContain('attr__class="doc-thumb"');
    expect(chain).toContain('attr__id="thumb-9"');
    expect(chain).toContain('nth-child="2"');
    expect(chain).toContain("div.reader-pane");
  });

  it("D3: attr__text is treated as an attr__ channel, not mangled as bare text=", () => {
    // The round-1 /text="…"/g regex matched INSIDE attr__text="…". With the
    // boundary-aware scrub, attr__text (non-allowlisted) is dropped cleanly and
    // a separate bare text= channel is independently emptied — neither corrupts
    // the other's boundary.
    const out = sanitizeOutgoingEvent(
      event({
        $elements_chain: `span.lbl:attr__text="${SENTINEL}"text="${SENTINEL}"nth-child="1"`,
      }),
    )!;
    const chain = out.properties.$elements_chain as string;
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    // structure intact and well-formed (no merged/broken attribute tokens)
    expect(chain).toContain("span.lbl");
    expect(chain).toContain('nth-child="1"');
    expect(chain).toContain('attr__text=""');
    expect(chain).toContain('text=""');
  });

  it("escaped quotes inside chain values cannot leak the tail (round-2 critic find)", () => {
    // PostHog escapes an inner `"` as `\"` when serializing $elements_chain. A
    // value body of `[^"]*` stops at the first `\"` and leaks everything after
    // it — quoted reading content (speech, book titles, scare quotes) is
    // pervasive on a reading surface. The `(?:\\.|[^"\\])*` body spans escaped
    // quotes, so the whole value is scrubbed. Also exercises an adjacent attr
    // pair where the first value contains escaped quotes (boundary still holds).
    const out = sanitizeOutgoingEvent(
      event({
        $elements_chain:
          `p.passage:text="He whispered \\"${SENTINEL}\\" softly"` +
          `attr__title="caption \\"${SENTINEL}\\" end"attr__class="passage"`,
      }),
    )!;
    const chain = out.properties.$elements_chain as string;
    expect(JSON.stringify(out)).not.toContain(SENTINEL);
    expect(chain).not.toContain(SENTINEL);
    // structural attr survives; non-structural value fully emptied
    expect(chain).toContain("p.passage");
    expect(chain).toContain('attr__class="passage"');
  });
});

// ---------------------------------------------------------------------------
// SPR-04 — M3: custom content-property denylist (defense-in-depth, §9.0).
// ---------------------------------------------------------------------------
describe("sanitizeOutgoingEvent — custom content denylist (M3)", () => {
  it("strips denylisted content props but keeps structural props", () => {
    const out = sanitizeOutgoingEvent(
      event({
        // denylisted — would carry substrate free text if ever added to an event
        query: "the user's private research question",
        document_title: "Confidential Q3 strategy memo",
        passage_text: "a quoted paragraph from a paywalled book",
        note: "freeform user note",
        // allowlisted structural props from the real analytics.ts taxonomy
        question_length: 42,
        problem_length: 17,
        session_id: "sess-abc-123",
        investigation_id: "inv-9",
        has_passage: true,
        has_parent: false,
        block_type: "paragraph",
        page_index: 4,
      }),
    )!;
    const p = out.properties;
    // content scrubbed
    expect(p.query).toBeUndefined();
    expect(p.document_title).toBeUndefined();
    expect(p.passage_text).toBeUndefined();
    expect(p.note).toBeUndefined();
    // structural data survives — analytics still works
    expect(p.question_length).toBe(42);
    expect(p.problem_length).toBe(17);
    expect(p.session_id).toBe("sess-abc-123");
    expect(p.investigation_id).toBe("inv-9");
    expect(p.has_passage).toBe(true);
    expect(p.has_parent).toBe(false);
    expect(p.block_type).toBe("paragraph");
    expect(p.page_index).toBe(4);
  });

  it("never denylists $-prefixed PostHog-internal keys (e.g. $event_type survives)", () => {
    // `$` keys are owned by the URL/autocapture logic; structural ones like
    // $event_type must survive even though 'text'/'name' (their non-$ cousins)
    // are denylisted.
    const out = sanitizeOutgoingEvent(
      event({ $event_type: "click", $screen_name: "reader" }),
    )!;
    expect(out.properties.$event_type).toBe("click");
    expect(out.properties.$screen_name).toBe("reader");
  });
});
