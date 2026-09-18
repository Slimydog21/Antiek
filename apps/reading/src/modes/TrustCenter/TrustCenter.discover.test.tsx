import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("../../lib/api", () => ({ apiFetch: apiFetchMock }));

import TrustCenter from "./index";
import { PUBLIC_LANE_LABELS } from "../../lib/speakVocab";

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({
    ok: true,
    json: async () => ({
      differential_privacy_epsilon_budgets: {},
      deletion_sla_days: 30,
      substrate_controls: [],
      compliance_frameworks: [],
      loop_3_unlock_status: {},
    }),
  });
});
afterEach(cleanup);

describe("TrustCenter — Speak browse discoverability", () => {
  it("links logged-out visitors to /speak/browse", async () => {
    render(
      <MemoryRouter>
        <TrustCenter />
      </MemoryRouter>,
    );
    const link = await screen.findByTestId("trust-speak-browse-link");
    expect(link).toBeTruthy();
    expect(screen.getByText(PUBLIC_LANE_LABELS.discoverBrowseBlurb)).toBeTruthy();
    const a = screen.getByRole("link", { name: PUBLIC_LANE_LABELS.discoverBrowseLink });
    expect(a.getAttribute("href")).toBe("/speak/browse");
  });
});

