import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Topbar } from "../components/navigation/Topbar";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("./api", () => ({
  API_BASE: "",
  apiFetch: apiFetchMock,
}));
vi.mock("./posthogClient", () => ({
  posthogEnabled: false,
  posthog: { identify: vi.fn(), reset: vi.fn() },
}));

import { AuthProvider, useAuth } from "./auth";

const identity = {
  user_id: "usr_test",
  email: "reader@example.com",
  auth_method: "antiek_session_cookie",
  scopes: ["basic", "private_research"],
  is_operator: false,
};

function Harness() {
  const { state, signOut, signOutError } = useAuth();
  return (
    <>
      <output data-testid="auth-state">{state.status}</output>
      <Topbar onSignOut={signOut} signOutError={signOutError} />
    </>
  );
}

function renderHarness() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function openAndSignOut() {
  await waitFor(() => expect(screen.getByTestId("auth-state").textContent).toBe("authenticated"));
  fireEvent.click(screen.getByRole("button", { name: "Account" }));
  fireEvent.click(screen.getByText("Sign out"));
}

describe("durable logout", () => {
  beforeEach(() => apiFetchMock.mockReset());
  afterEach(cleanup);

  it("changes client state only after the server confirms 204", async () => {
    apiFetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => identity })
      .mockResolvedValueOnce({ ok: true, status: 204 });
    renderHarness();
    await openAndSignOut();

    await waitFor(() => expect(screen.getByTestId("auth-state").textContent).toBe("unauthenticated"));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it.each([
    ["401 response", () => Promise.resolve({ ok: false, status: 401 })],
    ["500 response", () => Promise.resolve({ ok: false, status: 500 })],
    ["network rejection", () => Promise.reject(new Error("offline"))],
  ])("keeps the authenticated state and exposes retry feedback on %s", async (_label, logout) => {
    apiFetchMock
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => identity })
      .mockImplementationOnce(logout);
    renderHarness();
    await openAndSignOut();

    expect((await screen.findByRole("alert")).textContent).toContain("session is still active");
    expect(screen.getByTestId("auth-state").textContent).toBe("authenticated");
    expect(screen.getByRole("menu")).not.toBeNull();
    expect(screen.getByText("Sign out")).not.toBeNull();
  });
});
