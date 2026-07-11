import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import NotDiamondShadowPanel from "./NotDiamondShadowPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("NotDiamondShadowPanel", () => {
  it("records shadow with kill switch off by default", async () => {
    const shadowFn = vi.fn(async () => ({
      enabled: false,
      authority: "shadow" as const,
      task: "general",
      local_model_id: "m1",
      nd_recommended_model_id: null,
      agreement: null,
      notes: ["kill_switch=off"],
    }));
    render(
      <NotDiamondShadowPanel
        shadowFn={shadowFn}
        initialLocalModel="m1"
        initialNdModel="nd-x"
      />,
    );
    fireEvent.click(screen.getByTestId("nd-shadow-run"));
    await waitFor(() => {
      expect(screen.getByTestId("nd-shadow-result")).toBeTruthy();
    });
    expect(shadowFn).toHaveBeenCalledWith({
      local_model_id: "m1",
      nd_recommended_model_id: "nd-x",
      enabled: false,
    });
    expect(screen.getByTestId("nd-shadow-authority").textContent).toMatch(
      /shadow/i,
    );
    expect(screen.getByTestId("nd-shadow-enabled-echo").textContent).toMatch(
      /off/i,
    );
  });

  it("surfaces errors without inventing success", async () => {
    const shadowFn = vi.fn(async () => {
      throw new Error("enabled=true requires explicit injected");
    });
    render(
      <NotDiamondShadowPanel shadowFn={shadowFn} initialLocalModel="m1" />,
    );
    fireEvent.click(screen.getByTestId("nd-shadow-enabled"));
    fireEvent.click(screen.getByTestId("nd-shadow-run"));
    await waitFor(() => {
      expect(screen.getByTestId("nd-shadow-error").textContent).toMatch(
        /injected/i,
      );
    });
    expect(screen.queryByTestId("nd-shadow-result")).toBeNull();
  });

  it("shows disagreement when shadow on with injectable result", async () => {
    const shadowFn = vi.fn(async () => ({
      enabled: true,
      authority: "shadow" as const,
      task: "general",
      local_model_id: "m1",
      nd_recommended_model_id: "m2",
      agreement: false,
      notes: [],
    }));
    render(
      <NotDiamondShadowPanel
        shadowFn={shadowFn}
        initialLocalModel="m1"
        initialNdModel="m2"
      />,
    );
    fireEvent.click(screen.getByTestId("nd-shadow-enabled"));
    fireEvent.click(screen.getByTestId("nd-shadow-run"));
    await waitFor(() => {
      expect(screen.getByTestId("nd-shadow-agreement").textContent).toMatch(
        /no/i,
      );
    });
    expect(shadowFn).toHaveBeenCalledWith({
      local_model_id: "m1",
      nd_recommended_model_id: "m2",
      enabled: true,
    });
  });
});
