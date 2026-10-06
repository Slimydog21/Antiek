import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { resetReadingStateBus, setReadingStateOwner } from "../../hooks/useReadingState";
import BookReader from "./index";

// Run the real API client and reader. Every transport response is a failure;
// these controls establish error behavior, never successful book availability.
const transport = vi.fn<typeof fetch>();
const documentId = "failure-control";
const privateDiagnostic = "controlled server diagnostic; not page copy";

function failedResponse(status: number): Response {
  return new Response(privateDiagnostic, { status });
}

function mountReader() {
  return render(<MemoryRouter><BookReader documentId={documentId} /></MemoryRouter>);
}

function metadataRequests() {
  return transport.mock.calls.filter(([input]) => String(input).endsWith(`/books/${documentId}`));
}

beforeEach(() => {
  transport.mockReset();
  transport.mockImplementation(async () => failedResponse(503));
  vi.stubGlobal("fetch", transport);
  setReadingStateOwner(null);
  resetReadingStateBus();
});

afterEach(() => {
  cleanup();
  resetReadingStateBus();
  vi.unstubAllGlobals();
});

describe("book failure UI through the real API client", () => {
  it.each([
    { status: 503, message: "Antiek is busy or restarting", retryable: true },
    { status: 401, message: "You're signed out", retryable: false },
    { status: 403, message: "This isn't available to your account", retryable: false },
    { status: 429, message: "Too many requests at once", retryable: true },
    { status: 500, message: "Something went wrong on Antiek's side", retryable: true },
  ])("describes HTTP $status and offers only its permitted retry", async ({ status, message, retryable }) => {
    transport.mockImplementation(async () => failedResponse(status));
    mountReader();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(message);
    expect(alert.textContent).toContain("Your library and notes are unchanged");
    expect(alert.textContent).not.toContain(privateDiagnostic);
    expect(alert.textContent).not.toContain(`HTTP ${status}`);
    expect(Boolean(within(alert).queryByRole("button", { name: "Try again" }))).toBe(retryable);
    expect(metadataRequests()).toHaveLength(1);
  });

  it("keeps a missing book distinct from an unavailable service", async () => {
    transport.mockImplementation(async () => failedResponse(404));
    mountReader();

    expect(await screen.findByRole("link", { name: "Go to the library" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("describes an actual rejected transport separately", async () => {
    transport.mockRejectedValue(new TypeError("controlled network failure"));
    mountReader();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Antiek can't be reached right now");
    expect(alert.textContent).not.toContain("controlled network failure");
    expect(within(alert).getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("preserves a 503 diagnosis even when its response body is interrupted", async () => {
    transport.mockImplementation(async () => {
      const response = failedResponse(503);
      vi.spyOn(response, "text").mockRejectedValue(new TypeError("controlled interrupted body"));
      return response;
    });
    mountReader();

    expect((await screen.findByRole("alert")).textContent).toContain("Antiek is busy or restarting");
  });

  it("retries the failed read and shows the next returned failure class", async () => {
    mountReader();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Antiek is busy or restarting");
    transport.mockImplementation(async () => failedResponse(401));

    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));

    const nextAlert = await screen.findByRole("alert");
    expect(nextAlert.textContent).toContain("You're signed out");
    expect(within(nextAlert).queryByRole("button", { name: "Try again" })).toBeNull();
    expect(metadataRequests()).toHaveLength(2);
    expect(transport.mock.calls.some(([input]) => String(input).includes("/books?status=servable"))).toBe(false);
  });
});
