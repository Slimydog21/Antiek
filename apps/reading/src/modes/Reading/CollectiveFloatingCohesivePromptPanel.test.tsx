import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CollectiveFloatingCohesivePromptPanel from "./CollectiveFloatingCohesivePromptPanel";

afterEach(() => {
  cleanup();
});

describe("CollectiveFloatingCohesivePromptPanel", () => {
  it("builds pack without live dispatch", async () => {
    render(<CollectiveFloatingCohesivePromptPanel />);
    fireEvent.click(screen.getByTestId("cfcp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("cfcp-dispatched").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("cfcp-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("cfcp-summary").textContent).toMatch(
        /cohesive pack/,
      );
    });
  });

  it("ack sets pack_ready still without dispatch", async () => {
    render(<CollectiveFloatingCohesivePromptPanel />);
    fireEvent.click(screen.getByTestId("cfcp-ack"));
    fireEvent.click(screen.getByTestId("cfcp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("cfcp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("cfcp-dispatched").textContent).toMatch(
        /false/,
      );
    });
  });

  it("blank prompt fails closed", async () => {
    render(<CollectiveFloatingCohesivePromptPanel />);
    fireEvent.change(screen.getByTestId("cfcp-prompt"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByTestId("cfcp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("cfcp-error").textContent).toMatch(
        /cohesive_prompt/,
      );
    });
  });
});
