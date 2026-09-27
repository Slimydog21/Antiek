import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import AppLegacy from "./AppLegacy";
import { useWorkspace } from "./workspace/WorkspaceStore";

vi.mock("./modes/ResearchWorkstation", () => ({
  default: () => <p>Research rollback route</p>,
}));
vi.mock("./modes/WrestleApp", () => ({
  default: () => <p>Wrestle rollback route</p>,
}));
vi.mock("./modes/Login", () => ({
  default: () => <p>Login route</p>,
}));
vi.mock("./workspace/PanelLayoutPanel", () => ({ PanelLayoutPanel: () => null }));

function renderRoute(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppLegacy /></MemoryRouter>);
}

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
});

describe("AppLegacy workspace rollback", () => {
  it.each([
    ["/", "Research rollback route"],
    ["/wrestle", "Wrestle rollback route"],
  ])("keeps one workspace layout around the %s critical route", (path, content) => {
    renderRoute(path);
    screen.getByText(content);
    expect(screen.getAllByLabelText("Left dock")).toHaveLength(1);
  });

  it("keeps login outside the workspace layout", () => {
    renderRoute("/login");
    screen.getByText("Login route");
    expect(screen.queryByLabelText("Left dock")).toBeNull();
  });
});
