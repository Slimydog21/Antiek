import { act, render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspace } from "./WorkspaceStore";
import { useWorkspaceHydration } from "./useWorkspaceHydration";

let generation = 1;
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ sessionGeneration: generation }),
}));

let navigate: ReturnType<typeof useNavigate>;
function Harness() {
  navigate = useNavigate();
  useWorkspaceHydration();
  useEffect(() => undefined, []);
  return null;
}

describe("in-memory workspace route continuity", () => {
  beforeEach(() => {
    generation = 1;
    window.localStorage.clear();
    useWorkspace.getState().reset();
  });

  it("starts empty on shell mount and never hydrates a legacy descriptor", async () => {
    useWorkspace.getState().open("FakeChat", { prompt: "must disappear" }, { id: "legacy" });
    useWorkspace.getState().pin("legacy");
    window.localStorage.setItem("antiek.workspace.global", JSON.stringify({ panels: { legacy: { props: { html: "hostile" } } } }));

    render(<MemoryRouter><Harness /></MemoryRouter>);
    await waitFor(() => expect(useWorkspace.getState().panels).toEqual({}));
    expect(window.localStorage.getItem("antiek.workspace.global")).toBeNull();
  });

  it("carries only pinned descriptors across a same-tab route change", async () => {
    render(<MemoryRouter initialEntries={["/one"]}><Harness /></MemoryRouter>);
    await waitFor(() => expect(useWorkspace.getState().panels).toEqual({}));
    act(() => {
      useWorkspace.getState().open("FakeChat", {}, { id: "pinned" });
      useWorkspace.getState().pin("pinned");
      useWorkspace.getState().open("FakeSidebar", {}, { id: "temporary" });
      navigate("/two");
    });
    await waitFor(() => expect(Object.keys(useWorkspace.getState().panels)).toEqual(["pinned"]));
  });

  it("drops pinned descriptors when the auth generation changes", async () => {
    const view = render(<MemoryRouter><Harness /></MemoryRouter>);
    await waitFor(() => expect(useWorkspace.getState().panels).toEqual({}));
    act(() => {
      useWorkspace.getState().open("FakeChat", {}, { id: "pinned" });
      useWorkspace.getState().pin("pinned");
      generation = 2;
      view.rerender(<MemoryRouter><Harness /></MemoryRouter>);
    });
    await waitFor(() => expect(useWorkspace.getState().panels).toEqual({}));
  });
});
