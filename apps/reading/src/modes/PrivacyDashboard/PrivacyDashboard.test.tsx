import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

vi.mock("../../api/privacy", () => ({
  fetchPrivacySettings: vi.fn(),
  setPrivacySurface: vi.fn(),
}));

import { apiFetch } from "../../lib/api";
import { fetchPrivacySettings, setPrivacySurface } from "../../api/privacy";
import PrivacyDashboard from "./index";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const trustCenter = {
  differential_privacy_epsilon_budgets: {
    skill_invocation_frequency: 2,
    source_tier_preference: 1,
    query_content_telemetry: 0,
  },
  deletion_sla_days: 30,
  substrate_controls: ["encryption at rest (per-graph keys via KMS)"],
  compliance_frameworks: ["GDPR Article 13/14 transparency"],
  loop_3_unlock_status: {},
};

const surfaces = [
  {
    surface_name: "skill_invocation_frequency",
    sensitivity: "low" as const,
    epsilon_per_day: 2,
    opt_in_required: false,
    description:
      "Which substrate skills fire and at what rate. Low sensitivity; " +
      "the DP randomizer ensures no single invocation is identifying.",
    enabled: true,
    default_enabled: true,
  },
  {
    surface_name: "source_tier_preference",
    sensitivity: "medium" as const,
    epsilon_per_day: 1,
    opt_in_required: true,
    description:
      "Which source tiers (Tier 1 = peer-reviewed primary, " +
      "Tier 5 = anonymous) you accept versus reject.",
    enabled: false,
    default_enabled: false,
  },
  {
    surface_name: "query_content_telemetry",
    sensitivity: "forbidden" as const,
    epsilon_per_day: 0,
    opt_in_required: false,
    description: "The text of your research queries. NOT COLLECTED.",
    enabled: false,
    default_enabled: false,
  },
];

describe("PrivacyDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/trust-center") return response(trustCenter);
      if (url === "/trust-center/deletion-requests") {
        return response({ requests: [] });
      }
      return response({ detail: "unexpected call" }, 404);
    });
    vi.mocked(fetchPrivacySettings).mockResolvedValue({
      surfaces,
      count: surfaces.length,
    });
  });

  afterEach(cleanup);

  it("renders a toggle per toggleable surface with registry-derived state", async () => {
    render(<PrivacyDashboard />);

    const skill = await screen.findByRole("switch", {
      name: "skill invocation frequency telemetry",
    });
    expect(skill.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("on by default")).toBeTruthy();

    const tier = await screen.findByRole("switch", {
      name: "source tier preference telemetry",
    });
    expect(tier.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("off by default (opt-in)")).toBeTruthy();

    // ε badges + trust-center readout survive.
    expect(screen.getByText("ε = 2/day")).toBeTruthy();
    expect(screen.getByText("ε = 1/day")).toBeTruthy();
    expect(screen.getByText(/substrate-wide daily ε total: 3\.00/)).toBeTruthy();
    expect(fetchPrivacySettings).toHaveBeenCalledTimes(1);
  });

  it("locks the forbidden surface: no toggle, 'never collected' badge", async () => {
    render(<PrivacyDashboard />);

    await screen.findByRole("switch", {
      name: "skill invocation frequency telemetry",
    });
    expect(
      screen.queryByRole("switch", { name: "query content telemetry telemetry" }),
    ).toBeNull();
    expect(screen.getByText(/never collected \(architectural\)/)).toBeTruthy();
    expect(screen.getByText("never enabled")).toBeTruthy();
  });

  it("PUTs on toggle change with optimistic update", async () => {
    const user = userEvent.setup();
    vi.mocked(setPrivacySurface).mockResolvedValue({
      ...surfaces[0],
      enabled: false,
    });
    render(<PrivacyDashboard />);

    const skill = await screen.findByRole("switch", {
      name: "skill invocation frequency telemetry",
    });
    await user.click(skill);

    // Optimistic: the switch flips before the PUT resolves.
    expect(skill.getAttribute("aria-checked")).toBe("false");
    await waitFor(() =>
      expect(setPrivacySurface).toHaveBeenCalledWith(
        "skill_invocation_frequency",
        false,
      ),
    );
    // Server row (enabled: false) is adopted on resolve.
    expect(skill.getAttribute("aria-checked")).toBe("false");
    expect(
      screen.getAllByText("off — opt-out recorded").length,
    ).toBeGreaterThan(0);
  });

  it("rolls back the toggle when the PUT fails and surfaces the error", async () => {
    const user = userEvent.setup();
    vi.mocked(setPrivacySurface).mockRejectedValue(
      new Error("privacy settings API 500"),
    );
    render(<PrivacyDashboard />);

    const skill = await screen.findByRole("switch", {
      name: "skill invocation frequency telemetry",
    });
    await user.click(skill);

    // Optimistic off-state is rolled back on failure.
    await waitFor(() =>
      expect(skill.getAttribute("aria-checked")).toBe("true"),
    );
    expect(screen.getByText(/privacy settings API 500/)).toBeTruthy();
  });
});
