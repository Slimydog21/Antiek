import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import ProjectTree from "./ProjectTree";
import type { Workflow } from "./workflowTaxonomy";
import { usePinned } from "../components/navigation/pinnedStore";
import { useWorkspace } from "../workspace/WorkspaceStore";

const { openDocumentMock } = vi.hoisted(() => ({
  openDocumentMock: vi.fn(),
}));

vi.mock("../lib/openDocument", async (orig) => ({
  ...(await orig<typeof import("../lib/openDocument")>()),
  useOpenDocument: () => openDocumentMock,
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderTree(workflow: Exclude<Workflow, "shared"> = "read") {
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <ProjectTree workflow={workflow} />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  openDocumentMock.mockReset();
  usePinned.getState().clear();
  useWorkspace.getState().reset();
});

afterEach(cleanup);

describe("ProjectTree workflow actions", () => {
  it("opens a document through the one Reader door on normal click", () => {
    renderTree("read");

    fireEvent.click(screen.getByText("Kalshi liquidity preprint.pdf"));

    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("kalshi-paper");
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });

  it("opens a document in inspect mode on Cmd/Ctrl-click instead of a PDF panel", () => {
    renderTree("read");

    fireEvent.click(screen.getByText("Kalshi liquidity preprint.pdf"), {
      metaKey: true,
    });

    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("kalshi-paper", {
      mode: "inspect",
    });
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });

  it("floats investigations on Cmd/Ctrl-click and keeps normal click as route navigation", () => {
    renderTree("research");

    fireEvent.click(screen.getByText("NVDA Q4 risk model"), { ctrlKey: true });
    const floatingId = useWorkspace.getState().floatingIds[0];
    expect(useWorkspace.getState().panels[floatingId]).toMatchObject({
      kind: "Trajectory",
      props: { id: "nvda-q4" },
      mode: "floating",
      title: "NVDA Q4 risk model",
    });
    expect(screen.getByTestId("location").textContent).toBe("/library");

    fireEvent.click(screen.getByText("Web gaming 2026"));
    expect(screen.getByTestId("location").textContent).toBe(
      "/inv/web-gaming-2026",
    );
  });

  it("pins item-specific rows with accessible labels and moves them above Recent", () => {
    renderTree("read");

    fireEvent.click(screen.getByLabelText("Pin Kalshi liquidity preprint.pdf"));

    expect(usePinned.getState().isPinned("document:kalshi-paper")).toBe(true);
    expect(
      screen.getByLabelText("Unpin Kalshi liquidity preprint.pdf"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /Pinned\s*1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Recent\s*1/ })).toBeTruthy();
  });
});
