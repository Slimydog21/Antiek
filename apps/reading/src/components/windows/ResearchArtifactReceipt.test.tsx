import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import ResearchArtifactReceipt from "./ResearchArtifactReceipt";

afterEach(() => cleanup());

describe("ResearchArtifactReceipt", () => {
  it("links artifact and twin notes through investigation-scoped HTML routes", () => {
    render(
      <MemoryRouter>
        <ResearchArtifactReceipt
          investigationId="inv child/1"
          artifactPath="/tmp/artifacts/inv-child.html"
          twinNotesPath="/tmp/artifacts/inv-child.notes.html"
          documentId="doc-1"
          pageIndex={2}
        />
      </MemoryRouter>,
    );

    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links[0].getAttribute("href")).toBe("/research/inv%20child%2F1/artifact/html");
    expect(links[1].getAttribute("href")).toBe("/research/inv%20child%2F1/artifact/twin-notes.html");
  });
});
