import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import NotebookLoopNav from "./NotebookLoopNav";

describe("NotebookLoopNav", () => {
  it("links research, write handoff, and notebooks index", () => {
    render(
      <MemoryRouter>
        <NotebookLoopNav investigationId="inv-abc" canWrite />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("notebook-loop-nav")).toBeTruthy();
    expect(screen.getByTestId("auto-notebook-back-to-research").getAttribute("href")).toBe(
      "/inv/inv-abc",
    );
    expect(screen.getByTestId("auto-notebook-continue-write").getAttribute("href")).toBe(
      "/write?investigation=inv-abc",
    );
    expect(screen.getByTestId("auto-notebook-continue-write").textContent).toMatch(
      /continue in Write/i,
    );
    expect(screen.getByTestId("auto-notebook-notebooks-index").getAttribute("href")).toBe(
      "/notebooks",
    );
  });
});
