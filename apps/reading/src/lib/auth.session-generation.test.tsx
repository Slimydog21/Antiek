import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWindows } from "../workspace/windowsStore";
import { AuthProvider, useAuth } from "./auth";

function identityResponse(userId: string): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      user_id: userId,
      email: `${userId}@example.test`,
      auth_method: "session_cookie",
    }),
  } as Response;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="generation">{auth.sessionGeneration}</span>
      <span data-testid="user">
        {auth.state.status === "authenticated" ? auth.state.identity.user_id : auth.state.status}
      </span>
      <button type="button" onClick={() => void auth.refresh()}>
        refresh
      </button>
      <button type="button" onClick={() => void auth.signOut()}>
        sign out
      </button>
    </div>
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AuthProvider private-window invalidation", () => {
  it("closes private windows and increments generation on account identity change", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(identityResponse("alice"));
    const reset = vi.spyOn(useWindows.getState(), "reset");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("alice"));
    expect(screen.getByTestId("generation").textContent).toBe("1");
    expect(reset).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValueOnce(identityResponse("bob"));
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("bob"));
    expect(screen.getByTestId("generation").textContent).toBe("2");
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it("ignores an older refresh response that arrives after a newer identity", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(identityResponse("alice"));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("alice"));

    const older = deferred<Response>();
    const newer = deferred<Response>();
    fetchMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    newer.resolve(identityResponse("bob"));
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("bob"));
    older.resolve(identityResponse("mallory"));
    await Promise.resolve();
    expect(screen.getByTestId("user").textContent).toBe("bob");
    expect(screen.getByTestId("generation").textContent).toBe("2");
  });

  it("invalidates immediately and suppresses refresh while sign-out is in flight", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(identityResponse("alice"));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("alice"));

    const logout = deferred<Response>();
    fetchMock.mockReturnValueOnce(logout.promise);
    fireEvent.click(screen.getByRole("button", { name: "sign out" }));
    expect(screen.getByTestId("user").textContent).toBe("unauthenticated");
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    logout.resolve({ ok: true, status: 204 } as Response);
    await Promise.resolve();
    expect(screen.getByTestId("user").textContent).toBe("unauthenticated");
  });
});
