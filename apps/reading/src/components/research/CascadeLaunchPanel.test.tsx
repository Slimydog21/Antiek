import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CascadeLaunchPanel from "./CascadeLaunchPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CascadeLaunchPanel", () => {
  it("launches via injectable launchFn with selected source_policy", async () => {
    const launchFn = vi.fn(async () => ({
      raw: { launched: true },
      source_policy: ["arxiv", "substack"] as const,
      require_source_preflight: true,
      source_preflight: {
        source_policy: ["arxiv", "substack"],
        source_receipt_id: "rcpt-1",
      },
    }));
    render(
      <CascadeLaunchPanel
        launchFn={launchFn as never}
        initialRootId="root-1"
        initialPolicies={["arxiv", "substack"]}
        initialRequirePreflight={true}
      />,
    );
    fireEvent.click(screen.getByTestId("cascade-launch-run"));
    await waitFor(() => {
      expect(screen.getByTestId("cascade-launch-result")).toBeTruthy();
    });
    expect(launchFn).toHaveBeenCalledWith({
      root_id: "root-1",
      source_policy: ["arxiv", "substack"],
      require_source_preflight: true,
      per_research_budget_usd: 0.5,
    });
    expect(screen.getByTestId("cascade-launch-policy").textContent).toMatch(
      /arxiv/,
    );
    expect(screen.getByTestId("cascade-launch-receipt").textContent).toMatch(
      /rcpt-1/,
    );
  });

  it("surfaces require-preflight without policy as error without inventing success", async () => {
    const launchFn = vi.fn(async () => {
      throw new Error(
        "source_policy is required when require_source_preflight is true",
      );
    });
    render(
      <CascadeLaunchPanel
        launchFn={launchFn as never}
        initialRootId="root-1"
        initialPolicies={[]}
        initialRequirePreflight={true}
      />,
    );
    fireEvent.click(screen.getByTestId("cascade-launch-run"));
    await waitFor(() => {
      expect(screen.getByTestId("cascade-launch-error").textContent).toMatch(
        /source_policy is required/i,
      );
    });
    expect(screen.queryByTestId("cascade-launch-result")).toBeNull();
  });

  it("clears result when source toggles change", async () => {
    const launchFn = vi.fn(async () => ({
      raw: { launched: true },
      source_policy: ["web"] as const,
      require_source_preflight: false,
      source_preflight: null,
    }));
    render(
      <CascadeLaunchPanel
        launchFn={launchFn as never}
        initialRootId="r"
        initialPolicies={["web"]}
        initialRequirePreflight={false}
      />,
    );
    fireEvent.click(screen.getByTestId("cascade-launch-run"));
    await waitFor(() => {
      expect(screen.getByTestId("cascade-launch-result")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("cascade-launch-src-arxiv"));
    expect(screen.queryByTestId("cascade-launch-result")).toBeNull();
  });
});
