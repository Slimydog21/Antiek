import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PromptProjectionPanel from "./PromptProjectionPanel";
import { computeUsageBar } from "../../api/promptProjection";

afterEach(() => {
  cleanup();
});

describe("PromptProjectionPanel", () => {
  it("projects exceed from fields", async () => {
    render(
      <PromptProjectionPanel
        initialDailyCapUsd="10"
        initialSpentUsd="8"
        initialLowUsd="1"
        initialHighUsd="3"
      />,
    );
    fireEvent.click(screen.getByTestId("pp-run"));
    await waitFor(() => {
      expect(screen.getByTestId("pp-would-exceed").textContent).toMatch(
        /true/,
      );
    });
  });

  it("shows null would_exceed when remaining unknown", async () => {
    render(
      <PromptProjectionPanel
        initialDailyCapUsd=""
        initialSpentUsd=""
        initialHighUsd="2"
        initialLowUsd="1"
      />,
    );
    fireEvent.click(screen.getByTestId("pp-run"));
    await waitFor(() => {
      expect(screen.getByTestId("pp-would-exceed").textContent).toMatch(
        /null/,
      );
    });
  });

  it("uses injected bar", async () => {
    const bar = computeUsageBar({ daily_cap_usd: 10, spent_usd: 1 });
    render(
      <PromptProjectionPanel
        bar={bar}
        initialHighUsd="2"
        initialLowUsd="1"
      />,
    );
    expect(screen.getByTestId("pp-bar-injected").textContent).toMatch(
      /remaining=9/,
    );
    fireEvent.click(screen.getByTestId("pp-run"));
    await waitFor(() => {
      expect(screen.getByTestId("pp-would-exceed").textContent).toMatch(
        /false/,
      );
    });
  });

  it("surfaces finite money errors", async () => {
    render(
      <PromptProjectionPanel
        initialDailyCapUsd="10"
        initialSpentUsd="1"
        initialHighUsd="NaN"
      />,
    );
    fireEvent.click(screen.getByTestId("pp-run"));
    await waitFor(() => {
      expect(screen.getByTestId("pp-error").textContent).toMatch(/finite/);
    });
  });
});
