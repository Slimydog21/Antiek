/**
 * WorkCard.test.tsx — Read SPR-09 M2 acceptance.
 *
 * Load-bearing claims:
 *  - a servable work shows title/author/source/servability and a "Read"
 *    affordance that fires onRead;
 *  - a gated work shows a "Claim to read" affordance that fires onClaim, NEVER
 *    onRead — and the card carries no body text (§9.0: the payload has none, the
 *    card requests none);
 *  - a taken-down work is non-actionable (disabled).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { BookSummary } from "../../api/books";
import WorkCard from "./WorkCard";

const servable: BookSummary = {
  document_id: "doc-s",
  title: "A Servable Title",
  author: "Ada Author",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 120,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

const gated: BookSummary = {
  document_id: "doc-g",
  title: "A Gated Title",
  author: "Bee Author",
  servability: "gated_metadata_only",
  servable_full_text: false,
  page_count: 0,
  cover_uri: null,
  ip_holder_id: "ip-1",
  taken_down: false,
};

const removed: BookSummary = {
  ...gated,
  document_id: "doc-x",
  title: "A Removed Title",
  servability: "taken_down",
  taken_down: true,
};

const privateAuthored: BookSummary = {
  ...gated,
  document_id: "doc-private",
  title: "Private Field Notes",
  author: null,
  servability: "private_authored",
  ip_holder_id: null,
};

afterEach(cleanup);

describe("WorkCard", () => {
  it("offers Read for private metadata without public full-text permission", () => {
    const onRead = vi.fn();
    const onClaim = vi.fn();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Unexpected card request"));
    try {
      render(<WorkCard work={privateAuthored} onRead={onRead} onClaim={onClaim} />);
      expect(screen.getByText("Private authored")).toBeTruthy();
      expect(screen.getByText("Your private document")).toBeTruthy();
      expect(screen.getByText("Read")).toBeTruthy();
      expect(screen.queryByText("Claim to read")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Read Private Field Notes" }));
      expect(onRead).toHaveBeenCalledOnce();
      expect(onRead).toHaveBeenCalledWith("doc-private");
      expect(onClaim).not.toHaveBeenCalled();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(privateAuthored.servable_full_text).toBe(false);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("names the private Read action with the author when present", () => {
    render(<WorkCard work={{ ...privateAuthored, author: "Ada Author" }} />);
    expect(screen.getByRole("button", { name: "Read Private Field Notes by Ada Author" })).toBeTruthy();
  });

  it("keeps a taken-down private work non-actionable", () => {
    const onRead = vi.fn();
    const onClaim = vi.fn();
    render(<WorkCard work={{ ...privateAuthored, taken_down: true }} onRead={onRead} onClaim={onClaim} />);
    const button = screen.getByRole("button", { name: "Private Field Notes — removed from the shelf" });
    expect(button).toBeInstanceOf(HTMLButtonElement);
    expect(button).toHaveProperty("disabled", true);
    expect(screen.getByText("Removed")).toBeTruthy();
    fireEvent.click(button);
    expect(onRead).not.toHaveBeenCalled();
    expect(onClaim).not.toHaveBeenCalled();
  });

  it("shows title, author, source and servability for a servable work", () => {
    render(<WorkCard work={servable} />);
    // The title renders twice (the decorative cover spine + the caption); both
    // present is correct, so assert at least one and rely on the accessible name.
    expect(screen.getAllByText("A Servable Title").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Read A Servable Title by Ada Author/ })).toBeTruthy();
    expect(screen.getByText(/Ada Author/)).toBeTruthy();
    // "Public domain" appears as both the servability tag and the source line.
    expect(screen.getAllByText("Public domain").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Read")).toBeTruthy(); // affordance label
  });

  it("a servable work fires onRead, not onClaim", () => {
    const onRead = vi.fn();
    const onClaim = vi.fn();
    render(<WorkCard work={servable} onRead={onRead} onClaim={onClaim} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onRead).toHaveBeenCalledWith("doc-s");
    expect(onClaim).not.toHaveBeenCalled();
  });

  it("a gated work offers Claim to read and fires onClaim, never onRead (§9.0)", () => {
    const onRead = vi.fn();
    const onClaim = vi.fn();
    render(<WorkCard work={gated} onRead={onRead} onClaim={onClaim} />);
    expect(screen.getByText("Claim to read")).toBeTruthy();
    expect(screen.getByText("Preview only")).toBeTruthy(); // servability tag
    fireEvent.click(screen.getByRole("button"));
    expect(onClaim).toHaveBeenCalledWith("doc-g");
    expect(onRead).not.toHaveBeenCalled();
  });

  it("a gated card renders only metadata — no body text leaks", () => {
    // The BookSummary shape carries no body field; assert the card surfaces only
    // the known metadata and nothing that could be a body.
    const { container } = render(<WorkCard work={gated} />);
    expect(container.textContent).toContain("A Gated Title");
    expect(container.textContent).toContain("Bee Author");
    // No accidental rendering of any non-metadata key.
    expect(container.textContent).not.toMatch(/full_text|raw_text|body/i);
  });

  it("a taken-down work is non-actionable", () => {
    const onRead = vi.fn();
    const onClaim = vi.fn();
    render(<WorkCard work={removed} onRead={onRead} onClaim={onClaim} />);
    const btn = screen.getByRole("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onRead).not.toHaveBeenCalled();
    expect(onClaim).not.toHaveBeenCalled();
  });
});
