import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ModelDecisionPromptComposePanel from "./ModelDecisionPromptComposePanel";

afterEach(() => {
  cleanup();
});

describe("ModelDecisionPromptComposePanel", () => {
  it("composes would_exceed for pro model over remaining", async () => {
    render(
      <ModelDecisionPromptComposePanel
        initialSelected="pro-1"
        initialCap="10"
        initialSpent="8"
      />,
    );
    fireEvent.click(screen.getByTestId("mdpc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mdpc-would-exceed").textContent).toMatch(
        /true/,
      );
    });
  });

  it("shows null when cap blank", async () => {
    render(
      <ModelDecisionPromptComposePanel
        initialSelected="flash-1"
        initialCap=""
        initialSpent=""
      />,
    );
    fireEvent.click(screen.getByTestId("mdpc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mdpc-would-exceed").textContent).toMatch(
        /null/,
      );
    });
  });

  it("surfaces missing model error", async () => {
    render(
      <ModelDecisionPromptComposePanel initialSelected="nope" />,
    );
    fireEvent.click(screen.getByTestId("mdpc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mdpc-error").textContent).toMatch(/not found/);
    });
  });
});
