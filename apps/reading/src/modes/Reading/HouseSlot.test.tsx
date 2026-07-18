/**
 * HouseSlot.test.tsx — SPR-07 M4 acceptance (declutter the doubled provenance,
 * never blank).
 *
 * Load-bearing claims (asserted, not eyeballed):
 *  - the PROMO card no longer says "from the library" TWICE. Before SPR-07 the
 *    phrase appeared in both the aria-label AND, redundantly, suffixed onto the
 *    visible author line. Now the provenance is a SINGLE phrase (in the
 *    aria-label); the visible author line is the author alone.
 *  - the slot NEVER blanks: BOTH fills render real content — the promo card
 *    renders its title/author/recommendation tag, and the no-promo neutral card
 *    renders the "From the library" tag (the text the out-of-scope AdBorder /
 *    WindowAdBorder never-blank guards assert against — kept verbatim).
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import HouseSlot from "./HouseSlot";

afterEach(cleanup);

describe("HouseSlot SPR-07 — single provenance + never blank", () => {
  it("the promo card states 'from the library' exactly ONCE (no doubled provenance)", () => {
    render(
      <HouseSlot
        promo={{ documentId: "doc-1", title: "On the Shortness of Life", author: "Seneca" }}
      />,
    );
    const card = screen.getByRole("button");
    // The single provenance lives on the accessible name (one phrase, once).
    expect(card.getAttribute("aria-label")).toBe(
      "Next read from the library: On the Shortness of Life",
    );
    // The VISIBLE author line is the author alone — the redundant
    // "· from the library" suffix is gone.
    expect(within(card).getByText("Seneca")).toBeTruthy();
    expect(within(card).queryByText(/· from the library/)).toBeNull();
    // The whole visible card mentions "from the library" zero times (the
    // provenance moved entirely to the aria-label); the recommendation tag
    // reads "Next read".
    expect(within(card).queryByText(/from the library/i)).toBeNull();
    expect(within(card).getByText("Next read")).toBeTruthy();
  });

  it("the promo card fully fills: title + author + recommendation tag all render", () => {
    render(
      <HouseSlot
        promo={{ documentId: "doc-2", title: "Meditations", author: "Marcus Aurelius" }}
      />,
    );
    expect(screen.getByText("Meditations")).toBeTruthy();
    expect(screen.getByText("Marcus Aurelius")).toBeTruthy();
    expect(screen.getByText("Next read")).toBeTruthy();
  });

  it("product-maps book marketplace port invent on promo card (not inventory-only)", () => {
    render(
      <HouseSlot
        promo={{ documentId: "doc-4", title: "Antiek Shelf", author: "Werner" }}
      />,
    );
    const invent = screen.getByTestId("house-slot-living-tv-art") as HTMLImageElement;
    expect(invent.getAttribute("src") ?? "").toMatch(
      /werner_book_marketplace_port_session_v1/,
    );
  });

  it("falls back to 'Unknown author' rather than blank when the author is null", () => {
    render(<HouseSlot promo={{ documentId: "doc-3", title: "Fragments", author: null }} />);
    expect(screen.getByText("Unknown author")).toBeTruthy();
  });

  it("the no-promo neutral card NEVER blanks — it renders the 'From the library' tag verbatim", () => {
    // The exact text the out-of-scope WindowAdBorder/AdBorder never-blank guards
    // assert (getAllByText("From the library")). This card is the default fill,
    // not a "no fill" branch — keeping it green keeps those guards green.
    render(<HouseSlot promo={null} />);
    expect(screen.getByText("From the library")).toBeTruthy();
  });
});
