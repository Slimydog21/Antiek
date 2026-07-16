/**
 * InvestigationsIndex.test.tsx — living-TV brand densify + start beat.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import InvestigationsIndex from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function renderIndex() {
  return render(
    <MemoryRouter>
      <InvestigationsIndex />
    </MemoryRouter>,
  );
}

describe("InvestigationsIndex — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome on the Investigations door", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ count: 0, investigations: [] }),
    });
    renderIndex();
    await waitFor(() => expect(screen.getByText("Investigations")).toBeTruthy());
    expect(screen.getByTestId("investigations-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "investigations-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });

  it("emits deep_research_start living-TV beat when starting an investigation", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ count: 0, investigations: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ investigation_id: "inv-new-1" }),
      });
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    renderIndex();
    await waitFor(() => expect(screen.getByText("Investigations")).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText(/What's the question/i), {
      target: { value: "How do transformers attend?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start investigation/i }));
    await waitFor(() => expect(seen).toContain("deep_research_start"));
    window.removeEventListener("antiek:werner-experience", onExp);
  });
});
