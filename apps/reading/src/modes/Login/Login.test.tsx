import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import Login from "./index";

vi.mock("../../lib/auth", () => ({
  authCallbackDiagnosticCode: () => null,
  authCallbackErrorDisplay: () => null,
  authLoginErrorDisplay: () => ({ message: "Login failed", hint: null }),
  requestMagicLink: vi.fn(),
  stripAuthCallbackErrorParam: () => "",
  useAuth: () => ({ state: { status: "anonymous" } }),
}));

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
  trackException: vi.fn(),
}));

afterEach(cleanup);

describe("Login", () => {
  it("uses the current Research home label in the brand subtitle", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    expect(screen.getByText("Research home")).toBeTruthy();
    expect(screen.queryByText("Research workstation")).toBeNull();
  });
});
