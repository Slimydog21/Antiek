import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import EvidencePassport from "./EvidencePassport";

afterEach(cleanup);

describe("EvidencePassport", () => {
  it("keeps reviewed custody separate from passage precision", () => {
    const { container } = render(
      <EvidencePassport
        sourceName="A Pattern Language"
        locator="Research 2 of 3"
        custody="hash-reviewed"
        precision="document-only"
      />,
    );
    expect(screen.getByText("Snapshot hash reviewed")).toBeTruthy();
    expect(screen.getByText("Document-level source")).toBeTruthy();
    expect(container.textContent).not.toMatch(/verified/i);
  });

  it("says when an exact passage anchor is pending without inventing an id", () => {
    render(
      <EvidencePassport
        sourceName="The Timeless Way of Building"
        locator="Page 12"
        custody="source-identified"
        precision="anchor-pending"
      />,
    );
    expect(screen.getByText("Exact passage anchor pending")).toBeTruthy();
    expect(screen.queryByText(/chunk-/i)).toBeNull();
  });

  it("degrades safely when the name is unavailable", () => {
    render(
      <EvidencePassport
        sourceName={null}
        custody="unavailable"
        precision="document-only"
      />,
    );
    expect(screen.getByText("Source name unavailable")).toBeTruthy();
    expect(screen.getByText("Source unavailable")).toBeTruthy();
  });

  it("does not imply serving rights when rights context is missing", () => {
    render(
      <EvidencePassport
        sourceName="Known document"
        custody="rights-unconfirmed"
        precision="document-only"
      />,
    );
    expect(screen.getByText("Rights unconfirmed")).toBeTruthy();
    expect(screen.queryByText("Source identified")).toBeNull();
  });
});
