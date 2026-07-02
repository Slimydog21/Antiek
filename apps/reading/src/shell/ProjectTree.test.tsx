import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import ProjectTree from "./ProjectTree";
import type { Workflow } from "./workflowTaxonomy";
import { usePinned } from "../components/navigation/pinnedStore";
import { useWorkspace } from "../workspace/WorkspaceStore";

const {
  apiFetchMock,
  listDeliverablesMock,
  listInvestigationsMock,
  openDocumentMock,
} = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  listDeliverablesMock: vi.fn(),
  listInvestigationsMock: vi.fn(),
  openDocumentMock: vi.fn(),
}));

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: apiFetchMock,
  listDeliverables: listDeliverablesMock,
  listInvestigations: listInvestigationsMock,
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
  apiFetchMock.mockReset().mockImplementation(async (path: string) => {
    if (String(path).startsWith("/documents")) {
      return {
        ok: true,
        json: async () => ({ documents: [] }),
      };
    }
    if (String(path) === "/notebooks") {
      return {
        ok: true,
        json: async () => ({ notebooks: [] }),
      };
    }
    return { ok: false, json: async () => ({}) };
  });
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
  listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  openDocumentMock.mockReset();
  usePinned.getState().clear();
  useWorkspace.getState().reset();
});

afterEach(cleanup);

describe("ProjectTree workflow actions", () => {
  it("loads live Read documents and notebooks", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).startsWith("/documents")) {
        return {
          ok: true,
          json: async () => ({
            documents: [
              { document_id: " doc-live ", title: "  Live document  " },
              { document_id: "doc-untitled", title: " " },
              { document_id: " ", title: "Skipped document" },
            ],
          }),
        };
      }
      if (String(path) === "/notebooks") {
        return {
          ok: true,
          json: async () => ({
            notebooks: [
              { notebook_id: " nb-live ", title: "  Live notebook  " },
              { notebook_id: " ", title: "Skipped notebook" },
            ],
          }),
        };
      }
      return { ok: false, json: async () => ({}) };
    });

    renderTree("read");

    expect(await screen.findByText("Live document")).toBeTruthy();
    expect(screen.getByText("Untitled source")).toBeTruthy();
    expect(screen.getByText("Live notebook")).toBeTruthy();
    expect(screen.queryByText("Skipped document")).toBeNull();
    expect(screen.queryByText("Skipped notebook")).toBeNull();
    expect(screen.getByRole("button", { name: /Recent\s*3/ })).toBeTruthy();
  });

  it("opens a live document through the one Reader door on normal click", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).startsWith("/documents")) {
        return {
          ok: true,
          json: async () => ({
            documents: [{ document_id: " doc-live ", title: "  Live document  " }],
          }),
        };
      }
      if (String(path) === "/notebooks") {
        return { ok: true, json: async () => ({ notebooks: [] }) };
      }
      return { ok: false, json: async () => ({}) };
    });

    renderTree("read");

    fireEvent.click(await screen.findByText("Live document"));

    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-live");
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });

  it("opens a live document in inspect mode on Cmd/Ctrl-click instead of a PDF panel", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).startsWith("/documents")) {
        return {
          ok: true,
          json: async () => ({
            documents: [{ document_id: "doc-inspect", title: "Inspect document" }],
          }),
        };
      }
      if (String(path) === "/notebooks") {
        return { ok: true, json: async () => ({ notebooks: [] }) };
      }
      return { ok: false, json: async () => ({}) };
    });

    renderTree("read");

    fireEvent.click(await screen.findByText("Inspect document"), {
      metaKey: true,
    });

    expect(openDocumentMock).toHaveBeenCalledTimes(1);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-inspect", {
      mode: "inspect",
    });
    expect(useWorkspace.getState().floatingIds).toEqual([]);
  });

  it("loads live Research investigations and opens the research workstation", async () => {
    listInvestigationsMock.mockResolvedValue({
      count: 4,
      investigations: [
        {
          investigation_id: " inv-live ",
          question: "  Live research  ",
          status: "in_progress",
        },
        {
          investigation_id: "inv-done",
          question: "Done research",
          status: "completed",
        },
        {
          investigation_id: "inv-untitled",
          question: " ",
          status: "stopped",
        },
        {
          investigation_id: " ",
          question: "Skipped research",
          status: "completed",
        },
      ],
    });

    renderTree("research");

    expect(await screen.findByText("Live research")).toBeTruthy();
    expect(await screen.findByText("Done research")).toBeTruthy();
    expect(await screen.findByText("Untitled research")).toBeTruthy();
    expect(screen.queryByText("Skipped research")).toBeNull();
    expect(screen.getByText("running")).toBeTruthy();
    expect(screen.getByText("done")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Recent\s*3/ })).toBeTruthy();

    fireEvent.click(screen.getByText("Live research"));
    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/inv/inv-live");
    });
  });

  it("floats live investigations on Cmd/Ctrl-click", async () => {
    listInvestigationsMock.mockResolvedValue({
      count: 1,
      investigations: [
        {
          investigation_id: "inv-float",
          question: "Floating research",
          status: "completed",
        },
      ],
    });

    renderTree("research");

    fireEvent.click(await screen.findByText("Floating research"), { ctrlKey: true });
    const floatingId = useWorkspace.getState().floatingIds[0];
    expect(useWorkspace.getState().panels[floatingId]).toMatchObject({
      kind: "Trajectory",
      props: { id: "inv-float" },
      mode: "floating",
      title: "Floating research",
    });
    expect(screen.getByTestId("location").textContent).toBe("/library");
  });

  it("pins item-specific rows with accessible labels and moves them above Recent", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).startsWith("/documents")) {
        return {
          ok: true,
          json: async () => ({
            documents: [{ document_id: "doc-pin", title: "Pinned document" }],
          }),
        };
      }
      if (String(path) === "/notebooks") {
        return { ok: true, json: async () => ({ notebooks: [] }) };
      }
      return { ok: false, json: async () => ({}) };
    });
    renderTree("read");

    await screen.findByText("Pinned document");
    fireEvent.click(screen.getByLabelText("Pin Pinned document"));

    expect(usePinned.getState().isPinned("document:doc-pin")).toBe(true);
    expect(screen.getByLabelText("Unpin Pinned document")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Pinned\s*1/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Recent\s*0/ })).toBeTruthy();
  });

  it("loads live Write pieces into the workflow tree and opens the Write loop", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 3,
      deliverables: [
        { deliverable_id: " dlv-live ", title: "  Live memo  " },
        { deliverable_id: " ", title: "Skipped memo" },
        { deliverable_id: "dlv-untitled", title: " " },
      ],
    });
    renderTree("write");

    expect(await screen.findByText("Live memo")).toBeTruthy();
    expect(await screen.findByText("Untitled piece")).toBeTruthy();
    expect(screen.queryByText("Skipped memo")).toBeNull();
    expect(screen.getByRole("button", { name: /Recent\s*2/ })).toBeTruthy();

    fireEvent.click(screen.getByText("Live memo"));
    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/write/dlv-live");
    });
  });

  it("opens Write pieces as floating previews on Cmd/Ctrl-click", async () => {
    listDeliverablesMock.mockResolvedValue({
      count: 1,
      deliverables: [{ deliverable_id: "dlv-preview", title: "Preview memo" }],
    });
    renderTree("write");

    fireEvent.click(await screen.findByText("Preview memo"), { metaKey: true });

    const floatingId = useWorkspace.getState().floatingIds[0];
    expect(useWorkspace.getState().panels[floatingId]).toMatchObject({
      kind: "DeliverablePreview",
      props: { deliverableId: "dlv-preview" },
      mode: "floating",
      title: "Preview memo",
    });
    expect(screen.getByTestId("location").textContent).toBe("/library");
  });
});
