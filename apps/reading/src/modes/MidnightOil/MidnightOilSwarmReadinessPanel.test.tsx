import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MidnightOilSwarmReadinessPanel from "./MidnightOilSwarmReadinessPanel";

afterEach(() => {
  cleanup();
});

describe("MidnightOilSwarmReadinessPanel", () => {
  it("unattended ready with consent and ack; live false", async () => {
    render(
      <MidnightOilSwarmReadinessPanel initialOperatorId="op-1" />,
    );
    fireEvent.click(screen.getByTestId("mosr-consent"));
    fireEvent.click(screen.getByTestId("mosr-ack"));
    fireEvent.click(screen.getByTestId("mosr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mosr-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("mosr-unattended").textContent).toMatch(
        /true/,
      );
    });
  });

  it("not ready without ack", async () => {
    render(
      <MidnightOilSwarmReadinessPanel initialOperatorId="op-1" />,
    );
    fireEvent.click(screen.getByTestId("mosr-consent"));
    fireEvent.click(screen.getByTestId("mosr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mosr-unattended").textContent).toMatch(
        /false/,
      );
      expect(screen.getByTestId("mosr-live").textContent).toMatch(/false/);
    });
  });

  it("surfaces empty operator error", async () => {
    render(<MidnightOilSwarmReadinessPanel initialOperatorId="" />);
    fireEvent.click(screen.getByTestId("mosr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mosr-error").textContent).toMatch(
        /operator_id/,
      );
    });
  });
});
