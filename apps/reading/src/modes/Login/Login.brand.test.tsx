/**
 * Login brand mark — session thinking pose is UI-consumed on the sign-in desk.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/auth", () => ({
  authCallbackErrorDisplay: () => ({ message: "", hint: null, code: null }),
  authLoginErrorDisplay: () => ({ message: "", hint: null, code: null }),
  approveLogin: vi.fn(),
  beginPasskeyLogin: vi.fn(),
  beginPasskeyRegistration: vi.fn(),
  finishPasskeyLogin: vi.fn(),
  finishPasskeyRegistration: vi.fn(),
  getPasskeyStatus: vi.fn(async () => ({ available: false })),
  claimLogin: vi.fn(),
  requestMagicLink: vi.fn(),
  useAuth: () => ({ state: { status: "anonymous" }, refresh: vi.fn() }),
}));

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
  trackException: vi.fn(),
}));

import Login from "./index";

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => cleanup());

describe("Login session brand", () => {
  it("renders the session thinking Werner mark on the sign-in desk", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );
    const mark = screen.getByTestId("login-werner-brand");
    expect(mark).toBeTruthy();
    expect(mark.getAttribute("src")).toBeTruthy();
  });
});
