import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PanelHost, type StarterPanel } from "./PanelHost";
import { PanelLayout } from "./PanelLayout";
import { useWorkspace } from "./WorkspaceStore";

vi.mock("./PanelLayoutPanel", () => ({ PanelLayoutPanel: () => null }));

const originalWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");
const starters: StarterPanel[] = [{
  kind: "InvestigationSidebar",
  mode: "docked-left",
  title: "Investigations",
  id: "test:investigation-sidebar",
}];

function mountRoute() {
  return render(
    <PanelLayout mainSlot={
      <PanelHost starters={starters}>
        <p>Research center</p>
      </PanelHost>
    } />,
  );
}

describe("PanelHost inside the app shell", () => {
  beforeEach(() => {
    useWorkspace.getState().reset();
  });

  afterEach(() => {
    useWorkspace.getState().reset();
    if (originalWidth) Object.defineProperty(window, "innerWidth", originalWidth);
    else Reflect.deleteProperty(window, "innerWidth");
  });

  it("renders the shared left dock once and still registers and cleans the route starter", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    const view = mountRoute();

    screen.getByText("Research center");
    expect(screen.getAllByLabelText("Left dock")).toHaveLength(1);
    expect(useWorkspace.getState().dockLeftIds).toEqual(["test:investigation-sidebar"]);

    view.unmount();
    expect(useWorkspace.getState().dockLeftIds).toEqual([]);
  });

  it("keeps the narrow-screen route visible without rendering docks", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    mountRoute();

    expect(screen.queryAllByLabelText("Left dock")).toHaveLength(0);
    expect(screen.getAllByText("Research center")).toHaveLength(1);
  });

  it("retains a pinned starter when its route unmounts", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    const view = mountRoute();
    useWorkspace.getState().pin("test:investigation-sidebar");

    view.unmount();
    expect(useWorkspace.getState().dockLeftIds).toEqual(["test:investigation-sidebar"]);
  });
});
