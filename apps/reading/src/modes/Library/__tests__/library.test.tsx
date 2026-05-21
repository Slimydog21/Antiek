// SPR-06 / M6 — Library unit tests.
//
// Coverage:
//   - deriveImportPhase maps real backend states (status + content_type)
//     to user-visible phases honestly. No synthetic timer is asserted.
//   - humanizeError maps known codes to consumer-readable strings;
//     unknown codes pass through with the raw code visible (rigor #1
//     intellectual honesty: we don't fake completeness).
//   - EmptyState renders the three suggested URLs and reports clicks
//     back through the suggestion callback.
//   - LibraryCard renders a "partial · paywall" tag when paywalled
//     metadata is set (rigor #1).
//   - LibraryCard fires `document_opened` via the parent onOpen
//     callback (M5 event emit contract — the parent decides whether
//     to call emitBehaviorEvent; the card itself just calls
//     onOpen(doc)).
//   - resolvePostLoginDestination honors new-user → /library landing
//     (M4 + rigor #5 defensibility).

import { afterEach, describe, expect, it, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Without explicit cleanup, jsdom retains the DOM across `render()`
// calls in the same file and `getByTestId` finds multiple matches.
afterEach(() => {
  cleanup();
});

import { deriveImportPhase, humanizeError } from "../ImportProgress";
import { EmptyState } from "../EmptyState";
import { LibraryCard } from "../LibraryCard";
import { resolvePostLoginDestination } from "../../../routing/postLogin";
import { _resetUserSettingsForTests, recordLastOpenedDocument, writeUserSettings } from "../../../settings/userSettings";

describe("deriveImportPhase — real backend phases, not synthetic", () => {
  it("maps pending status to pending phase", () => {
    expect(
      deriveImportPhase({ status: "pending", content_type: null }),
    ).toBe("pending");
  });

  it("maps running + no content_type to fetching", () => {
    expect(
      deriveImportPhase({ status: "running", content_type: null }),
    ).toBe("fetching");
  });

  it("maps running + known content_type to extracting", () => {
    expect(
      deriveImportPhase({ status: "running", content_type: "pdf" }),
    ).toBe("extracting");
  });

  it("maps succeeded to ready", () => {
    expect(
      deriveImportPhase({ status: "succeeded", content_type: "html_article" }),
    ).toBe("ready");
  });

  it("maps failed to failed regardless of content_type", () => {
    expect(
      deriveImportPhase({ status: "failed", content_type: "pdf" }),
    ).toBe("failed");
  });

  it("honors phaseHint when the future pipeline emits it", () => {
    expect(
      deriveImportPhase({ status: "running", content_type: "pdf", phaseHint: "embed" }),
    ).toBe("extracting");
    expect(
      deriveImportPhase({ status: "running", content_type: null, phaseHint: "fetch" }),
    ).toBe("fetching");
  });
});

describe("humanizeError — actionable messages, raw passthrough", () => {
  it("maps domain_banned to a try-again message", () => {
    expect(humanizeError("domain_banned", null)).toContain("rate-limiting");
  });

  it("maps low_word_count to a paywall hint", () => {
    expect(humanizeError("low_word_count", null)).toContain("paywall");
  });

  it("maps http_404 to a HTTP-coded message", () => {
    expect(humanizeError("http_404", null)).toContain("HTTP 404");
  });

  it("passes unknown codes through with the raw code visible", () => {
    const msg = humanizeError("totally_made_up_code", "and a detail");
    expect(msg).toContain("totally_made_up_code");
    expect(msg).toContain("and a detail");
  });
});

describe("EmptyState — three suggestions, click reports back", () => {
  it("renders three suggested URLs", () => {
    render(<EmptyState />);
    const buttons = screen.getAllByTestId("library-empty-suggestion");
    expect(buttons.length).toBe(3);
  });

  it("calls onSuggestionClick with the chosen URL", () => {
    const calls: string[] = [];
    render(<EmptyState onSuggestionClick={(url) => calls.push(url)} />);
    const buttons = screen.getAllByTestId("library-empty-suggestion");
    fireEvent.click(buttons[0]);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatch(/^https?:/);
  });
});

describe("LibraryCard — paywall surfaced honestly (rigor #1)", () => {
  const baseDoc = {
    document_id: "doc-test-1",
    title: "Some paywalled article",
    source_uri: "https://nytimes.com/some-article",
    document_type: "web_article",
    source_tier: 4,
  };

  it("renders a paywall tag when metadata.paywalled is true", () => {
    render(
      <MemoryRouter>
        <LibraryCard doc={{ ...baseDoc, metadata: { paywalled: true } }} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("library-card-paywall-tag")).toBeDefined();
  });

  it("does NOT render a paywall tag when metadata.paywalled is absent", () => {
    render(
      <MemoryRouter>
        <LibraryCard doc={{ ...baseDoc, metadata: { paywalled: false } }} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("library-card-paywall-tag")).toBeNull();
  });

  it("calls onOpen with the doc when the card is clicked (M5 emit contract)", () => {
    const opened: string[] = [];
    render(
      <MemoryRouter>
        <LibraryCard
          doc={baseDoc}
          onOpen={(d) => opened.push(d.document_id)}
        />
      </MemoryRouter>,
    );
    const card = screen.getByTestId("library-card");
    fireEvent.click(card);
    expect(opened).toEqual(["doc-test-1"]);
  });
});

describe("resolvePostLoginDestination — dual-market routing (rigor #5)", () => {
  beforeEach(() => {
    _resetUserSettingsForTests();
  });

  it("honors next= param when provided", () => {
    const out = resolvePostLoginDestination({ nextParam: "/wrestle/abc" });
    expect(out.path).toBe("/wrestle/abc");
    expect(out.reason).toBe("next_param_honored");
  });

  it("lands new users (no last-opened doc) at /library", () => {
    const out = resolvePostLoginDestination({});
    expect(out.path).toBe("/library");
    expect(out.reason).toBe("library_default_for_new_user");
  });

  it("lands existing users at /wrestle/<last-opened>", () => {
    recordLastOpenedDocument("doc-prev");
    const out = resolvePostLoginDestination({});
    expect(out.path).toBe("/wrestle/doc-prev");
    expect(out.reason).toBe("last_opened_document");
  });

  it("respects the explicit alwaysStartAtLibrary opt-in for existing users", () => {
    recordLastOpenedDocument("doc-prev");
    writeUserSettings({ alwaysStartAtLibrary: true });
    const out = resolvePostLoginDestination({});
    expect(out.path).toBe("/library");
    expect(out.reason).toBe("library_setting_opted_in");
  });

  it("treats next='/' the same as no next (fall through to inference)", () => {
    const out = resolvePostLoginDestination({ nextParam: "/" });
    expect(out.path).toBe("/library");
  });
});

describe("emit document_opened — closed-taxonomy assertion", () => {
  it("DOCUMENT_OPENED is in the closed behavior taxonomy", async () => {
    // Sanity check: the spec text claimed both document_imported and
    // document_opened are in the closed taxonomy. Only document_opened
    // actually is — this test guards the bit we CAN guarantee.
    const mod = await import("../../../lib/behaviorEvents");
    expect(mod.ALL_BEHAVIOR_EVENT_TYPES).toContain("document_opened");
  });

  it("document_imported is NOT in the closed taxonomy at SPR-06 closeout", async () => {
    // Honesty assertion (rigor #1): the sprint spec said it was;
    // it isn't. If a future sprint adds it (via taxonomy migration +
    // schema file), this test will flip and the LibraryGrid TODO
    // call site should start emitting.
    const mod = await import("../../../lib/behaviorEvents");
    expect(mod.ALL_BEHAVIOR_EVENT_TYPES).not.toContain("document_imported");
  });
});
