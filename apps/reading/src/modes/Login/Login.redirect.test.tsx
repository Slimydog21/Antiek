import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";

const auth = vi.hoisted(() => ({
  status: "authenticated",
  refresh: vi.fn().mockResolvedValue(undefined),
  requestMagicLink: vi.fn(),
  claimLogin: vi.fn(),
}));
vi.mock("../../lib/auth", async (original) => ({
  ...(await original<typeof import("../../lib/auth")>()),
  useAuth: () => ({ state: { status: auth.status }, refresh: auth.refresh }),
  getPasskeyStatus: vi.fn().mockResolvedValue({ available: false }),
  requestMagicLink: auth.requestMagicLink,
  claimLogin: auth.claimLogin,
}));
vi.mock("../../lib/analytics", () => ({ track: vi.fn(), trackException: vi.fn() }));
vi.mock("../../components/sketches", () => ({
  SketchCanvas: () => null,
  renderConstellation: vi.fn(),
  DEFAULT_CONSTELLATION_PARAMS: {},
}));
import Login from "./index";

function Destination() {
  const location = useLocation();
  return <output data-testid="destination">{location.pathname + location.search + location.hash}</output>;
}

function mountLogin(url: string, state: unknown = null) {
  window.history.replaceState({ usr: state }, "", url);
  return render(<BrowserRouter><Routes>
    <Route path="/login" element={<Login />} />
    <Route path="*" element={<Destination />} />
  </Routes></BrowserRouter>);
}

beforeEach(() => {
  auth.status = "authenticated";
  auth.requestMagicLink.mockReset();
  auth.claimLogin.mockReset();
});
afterEach(cleanup);

it.each(["/\\outside.example/path", "https://outside.example/path", "javascript:alert(1)"])("replaces invalid next %s with home", async (next) => {
  mountLogin(`/login?next=${encodeURIComponent(next)}`);
  await waitFor(() => expect(screen.getByTestId("destination").textContent).toBe("/"));
});

it("preserves an internal destination including its query and fragment", async () => {
  mountLogin(`/login?next=${encodeURIComponent("/notebooks?q=one#note")}`);
  await waitFor(() => expect(screen.getByTestId("destination").textContent).toBe("/notebooks?q=one#note"));
});

it("rejects a nonstring history-state destination", async () => {
  mountLogin("/login", { from: { pathname: "/unexpected" } });
  await waitFor(() => expect(screen.getByTestId("destination").textContent).toBe("/"));
});

it("uses a valid history-state destination when the query is absent", async () => {
  mountLogin("/login", { from: "/notes?tab=mine#last" });
  await waitFor(() => expect(screen.getByTestId("destination").textContent).toBe("/notes?tab=mine#last"));
});

it.each([false, true])("normalizes a claimed login destination before navigation (setup=%s)", async (setup) => {
  auth.status = "anonymous";
  auth.requestMagicLink.mockResolvedValue({ kind: "sent", attempt_id: "local-attempt", claim_secret: "local-secret" });
  auth.claimLogin.mockResolvedValue({ status: "authenticated", setup_passkey: setup, next: "/\\outside.example/path" });
  mountLogin("/login");
  fireEvent.change(screen.getByRole("textbox", { name: /email/i }), { target: { value: "reader@example.test" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue with email" }));
  await waitFor(() => {
    if (setup) {
      expect(window.location.pathname).toBe("/login");
      expect(new URLSearchParams(window.location.search).get("next")).toBe("/");
    } else {
      expect(screen.getByTestId("destination").textContent).toBe("/");
    }
  });
});

it.each([false, true])("normalizes a typed-code claim destination (setup=%s)", async (setup) => {
  auth.status = "anonymous";
  auth.requestMagicLink.mockResolvedValue({ kind: "sent", attempt_id: "local-attempt", claim_secret: "local-secret" });
  auth.claimLogin.mockResolvedValueOnce({ status: "pending" }).mockResolvedValue({
    status: "authenticated", setup_passkey: setup, next: "/\\outside.example/path",
  });
  mountLogin(`/login?next=${encodeURIComponent("/\\outside.example/path")}`);
  fireEvent.change(screen.getByRole("textbox", { name: /email/i }), { target: { value: "reader@example.test" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue with email" }));
  const code = await screen.findByRole("textbox", { name: "4-digit code from the email" });
  await waitFor(() => expect(auth.claimLogin).toHaveBeenCalledTimes(1));
  expect(auth.requestMagicLink).toHaveBeenCalledWith("reader@example.test", "/");
  fireEvent.change(code, { target: { value: "1234" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
  await waitFor(() => {
    if (setup) {
      expect(new URLSearchParams(window.location.search).get("setup")).toBe("passkey");
      expect(new URLSearchParams(window.location.search).get("next")).toBe("/");
    } else {
      expect(screen.getByTestId("destination").textContent).toBe("/");
    }
  });
  expect(auth.claimLogin).toHaveBeenLastCalledWith("local-attempt", "local-secret", "1234");
});
