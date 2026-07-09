import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { SourceIntentReceipt } from ".";

afterEach(() => cleanup());

describe("SourceIntentReceipt", () => {
  it("renders recorded source-pack intent without claiming execution", () => {
    render(<SourceIntentReceipt policy={["operator_corpus", "web", "arxiv", "substack"]} />);

    expect(screen.getByText("Source intent")).toBeTruthy();
    expect(screen.getByText("Corpus · Web · arXiv · Substack")).toBeTruthy();
    expect(screen.getByText(/recorded at start/i)).toBeTruthy();
    expect(screen.getByText(/execution receipts arrive separately/i)).toBeTruthy();
  });

  it("renders nothing when no source policy was recorded", () => {
    const { container } = render(<SourceIntentReceipt policy={[]} />);

    expect(container.textContent).toBe("");
  });
});
