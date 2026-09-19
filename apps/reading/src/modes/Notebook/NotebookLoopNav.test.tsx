import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import NotebookLoopNav, { writeHandoffHref } from "./NotebookLoopNav";

describe("NotebookLoopNav", () => {
  it("links research, distill hash, write handoff with title, and notebooks index", () => {
    render(
      <MemoryRouter>
        <NotebookLoopNav
          investigationId="inv-abc"
          canWrite
          writeTitle="What is the moat?"
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("notebook-loop-nav")).toBeTruthy();
    expect(screen.getByTestId("auto-notebook-back-to-research").getAttribute("href")).toBe(
      "/inv/inv-abc",
    );
    expect(screen.getByTestId("auto-notebook-open-distill").getAttribute("href")).toBe(
      "/inv/inv-abc#distill",
    );
    expect(screen.getByTestId("auto-notebook-continue-write").getAttribute("href")).toBe(
      writeHandoffHref("inv-abc", "What is the moat?"),
    );
    expect(screen.getByTestId("auto-notebook-continue-write").textContent).toMatch(
      /continue in Write/i,
    );
    expect(screen.getByTestId("auto-notebook-notebooks-index").getAttribute("href")).toBe(
      "/notebooks",
    );
  });

  it("writeHandoffHref omits empty title", () => {
    expect(writeHandoffHref("inv-1")).toBe("/write?investigation=inv-1");
    expect(writeHandoffHref("inv-1", "  ")).toBe("/write?investigation=inv-1");
  });
});
