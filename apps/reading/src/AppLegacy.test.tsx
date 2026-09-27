import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppLegacy from "./AppLegacy";
import { useWorkspace } from "./workspace/WorkspaceStore";

vi.mock("./modes/ResearchWorkstation", async () => {
  const { useAuth } = await import("./lib/auth");
  return {
    default: () => {
      const { state } = useAuth();
      return <p>{state.status === "authenticated" ? `Research owner ${state.identity.user_id}` : "Research pending"}</p>;
    },
  };
});
vi.mock("./modes/WrestleApp", () => ({
  default: () => <p>Wrestle rollback route</p>,
}));
vi.mock("./modes/Settings", () => ({
  default: () => <p>Settings rollback route</p>,
}));
vi.mock("./modes/Login", async () => {
  const { useLocation } = await import("react-router-dom");
  return { default: () => <p>Login route {useLocation().search}</p> };
});
vi.mock("./workspace/PanelLayoutPanel", () => ({ PanelLayoutPanel: () => null }));

let authStatus = 200;

function renderRoute(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppLegacy /></MemoryRouter>);
}

beforeEach(() => {
  authStatus = 200;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => authStatus === 200
    ? new Response(JSON.stringify({ user_id: "visual-owner", email: "visual@example.invalid", auth_method: "fixture" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    })
    : new Response(null, { status: 401 }));
});

afterEach(() => {
  cleanup();
  useWorkspace.getState().reset();
  vi.restoreAllMocks();
});

describe("AppLegacy workspace rollback", () => {
  it.each([
    ["/", "Research owner visual-owner"],
    ["/inv/inv-1", "Research owner visual-owner"],
    ["/wrestle", "Wrestle rollback route"],
    ["/wrestle/doc-1", "Wrestle rollback route"],
    ["/settings", "Settings rollback route"],
  ])("keeps one workspace layout around the %s critical route", async (path, content) => {
    renderRoute(path);
    await screen.findByText(content);
    expect(screen.getAllByLabelText("Left dock")).toHaveLength(1);
  });

  it("keeps login outside the workspace layout", async () => {
    renderRoute("/login");
    await screen.findByText(/Login route/);
    expect(screen.queryByLabelText("Left dock")).toBeNull();
  });

  it("sends an unauthenticated deep link to login before mounting workspace panels", async () => {
    authStatus = 401;
    renderRoute("/inv/inv-1");
    const login = await screen.findByText(/Login route/);
    expect(login.textContent).toContain("next=%2Finv%2Finv-1");
    await waitFor(() => expect(screen.queryByLabelText("Left dock")).toBeNull());
  });

  it("sends unauthenticated Settings to login before offering BYOT setup", async () => {
    authStatus = 401;
    renderRoute("/settings");
    const login = await screen.findByText(/Login route/);
    expect(login.textContent).toContain("next=%2Fsettings");
    expect(screen.queryByLabelText("Left dock")).toBeNull();
  });
});
