/**
 * ChaseSlideOver.brand.test — living-TV deep-research beats on chase spawn.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const startInvestigationMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  startInvestigation: startInvestigationMock,
}));

vi.mock("../../hooks/useInvestigationTree", () => ({
  recordSpawnRelationship: vi.fn(),
}));

import { WERNER_EXPERIENCE_EVENT } from "../../werner";
import ChaseSlideOver from "./ChaseSlideOver";

afterEach(() => {
  cleanup();
  startInvestigationMock.mockReset();
});

describe("ChaseSlideOver — living-TV deep-research beats", () => {
  it("emits deep_research_start on successful spawn", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: "inv-child-1",
    });
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);

    render(
      <MemoryRouter>
        <ChaseSlideOver
          spawnContext="A highlighted claim about wide-body jets"
          parentInvestigationId="inv-parent"
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Spawn investigation/i }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalled(),
    );
    expect(seen).toContain("deep_research_start");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
  });

  it("emits deep_research_error when spawn fails", async () => {
    startInvestigationMock.mockRejectedValue(new Error("backend down"));
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);

    render(
      <MemoryRouter>
        <ChaseSlideOver
          spawnContext="A highlighted claim about wide-body jets"
          parentInvestigationId="inv-parent"
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Spawn investigation/i }));
    await waitFor(() => expect(seen).toContain("deep_research_error"));
    expect(seen).toContain("deep_research_start");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
  });
});
