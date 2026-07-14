/**
 * Attribution.test.tsx — Read SPR-05 M3 acceptance.
 *
 * Attribution renders on ALL tiers, reading provenance off the GATE response:
 *  - arXiv (canonical_url present) → a "via arXiv" link to the canonical page +
 *    a tier chip + a license chip (when a license URI is known);
 *  - non-arXiv (tier null / canonical null) → nothing extra (the reader's
 *    servability badge stays the rights cue).
 * It never fabricates a license name: an unknown URI degrades to its terminal
 * segment, a known CC URI maps to a human chip.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import Attribution from "./Attribution";
import type { FullTextResponse } from "../../api/books";

afterEach(() => cleanup());

function body(over: Partial<FullTextResponse> = {}): FullTextResponse {
  return {
    document_id: "doc-1",
    servable: true,
    servability: "public_domain",
    full_text: "x",
    snippet: null,
    title: "T",
    author: "A",
    reason: "servable",
    tier: null,
    ad_eligible: true,
    canonical_url: null,
    license: null,
    ...over,
    chunks: over.chunks ?? [],
  };
}

describe("Attribution", () => {
  it("renders a via-arXiv link + tier + license chip for an arXiv T1 doc", () => {
    const { container, getByText } = render(
      <Attribution
        body={body({
          tier: "T1",
          canonical_url: "https://arxiv.org/abs/2401.00001",
          license: "https://creativecommons.org/publicdomain/zero/1.0/",
        })}
      />,
    );
    const link = getByText(/via arXiv/) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://arxiv.org/abs/2401.00001");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    // The license chip is a human label, not the raw URI.
    expect(getByText("CC0")).toBeTruthy();
    expect(container.querySelector("[aria-label='Attribution']")).toBeTruthy();
  });

  it("maps a CC-BY-NC URI to a human chip (T2)", () => {
    const { getByText } = render(
      <Attribution
        body={body({
          tier: "T2",
          canonical_url: "https://arxiv.org/abs/2402.00002",
          license: "https://creativecommons.org/licenses/by-nc/4.0/",
        })}
      />,
    );
    expect(getByText("CC BY-NC")).toBeTruthy();
    expect(getByText("Non-commercial")).toBeTruthy();
  });

  it("renders the via-arXiv link with no license chip when license is null (T3)", () => {
    const { getByText, queryByText } = render(
      <Attribution
        body={body({ tier: "T3", canonical_url: "https://arxiv.org/abs/2403.00003", license: null })}
      />,
    );
    expect(getByText(/via arXiv/)).toBeTruthy();
    expect(getByText("Rights reserved")).toBeTruthy();
    // No fabricated license chip.
    expect(queryByText(/^CC/)).toBeNull();
  });

  it("names the arXiv-default deposit license instead of a useless '1.0' chip (T3)", () => {
    // The arXiv default license URI ends in `.../1.0/`. The terminal-segment
    // fallback would render the chip text "1.0" (useless). The arXiv-default
    // branch must catch it BEFORE the fallback.
    const { getByText, queryByText } = render(
      <Attribution
        body={body({
          tier: "T3",
          canonical_url: "https://arxiv.org/abs/2404.00004",
          license: "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        })}
      />,
    );
    expect(getByText("arXiv default license")).toBeTruthy();
    expect(queryByText("1.0")).toBeNull();
  });

  it("renders nothing for a non-arXiv document (tier null, no canonical)", () => {
    const { container } = render(<Attribution body={body()} />);
    expect(container.querySelector("[aria-label='Attribution']")).toBeNull();
    expect(container.textContent).toBe("");
  });

  // ── licenseLabel if-chain ORDER (pins the dangerous orderings) ────────
  //
  // The chain checks the most-specific CC variants first; a careless reorder
  // would mislabel (e.g. /by-nc-sa matching /by, or /by-nc matching /by). Each
  // case below locks one branch and would FAIL if the chain were reordered.
  it.each([
    ["https://creativecommons.org/licenses/by-sa/4.0/", "CC BY-SA"],
    ["https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA"],
    ["https://creativecommons.org/licenses/by-nc-nd/4.0/", "CC BY-NC-ND"],
    ["https://creativecommons.org/licenses/by-nc/4.0/", "CC BY-NC"],
    ["https://creativecommons.org/licenses/by-nd/4.0/", "CC BY-ND"],
    ["https://creativecommons.org/licenses/by/4.0/", "CC BY"],
  ])("maps %s to the %s chip (order-locked)", (license, chip) => {
    const { getByText } = render(
      <Attribution
        body={body({ tier: "T1", canonical_url: "https://arxiv.org/abs/2405.00005", license })}
      />,
    );
    expect(getByText(chip)).toBeTruthy();
  });

  it("an unknown license URI degrades to its terminal segment, not a fabricated name", () => {
    const { getByText } = render(
      <Attribution
        body={body({
          tier: "T2",
          canonical_url: "https://arxiv.org/abs/2406.00006",
          license: "https://example.org/licenses/custom-thing/",
        })}
      />,
    );
    expect(getByText("CUSTOM-THING")).toBeTruthy();
  });
});
