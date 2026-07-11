import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilSwarmBriefPanel from "./MidnightOilSwarmBriefPanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilSwarmBriefPanel", () => {
  it("builds brief with live_execution_authorized false", async () => {
    render(
      <MidnightOilSwarmBriefPanel initialOperatorId="op-1" />,
    );
    fireEvent.change(screen.getByTestId("mo-swarm-ceiling"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("mo-swarm-approved"));
    fireEvent.click(screen.getByTestId("mo-swarm-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mo-swarm-live").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("mo-swarm-dispatch").textContent).toMatch(
        /true/,
      );
    });
  });

  it("dispatch_ready false without approval", async () => {
    render(
      <MidnightOilSwarmBriefPanel initialOperatorId="op-1" />,
    );
    fireEvent.change(screen.getByTestId("mo-swarm-ceiling"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("mo-swarm-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mo-swarm-dispatch").textContent).toMatch(
        /false/,
      );
    });
  });

  it("surfaces validation errors", async () => {
    render(<MidnightOilSwarmBriefPanel initialOperatorId="" />);
    fireEvent.click(screen.getByTestId("mo-swarm-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mo-swarm-error").textContent).toMatch(
        /operator_id/,
      );
    });
  });
});
