import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CompetitionGapResidualPlanPanel from "./CompetitionGapResidualPlanPanel";

afterEach(() => {
  cleanup();
});

describe("CompetitionGapResidualPlanPanel", () => {
  it("builds plan without mutating backlog", async () => {
    render(<CompetitionGapResidualPlanPanel />);
    fireEvent.click(screen.getByTestId("cgrp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("cgrp-mutated").textContent).toMatch(/false/);
      expect(screen.getByTestId("cgrp-summary").textContent).toMatch(
        /residual plan/,
      );
      expect(screen.getByTestId("cgrp-items").textContent).toMatch(/P0|P1/);
    });
  });

  it("surfaces JSON parse errors", async () => {
    render(<CompetitionGapResidualPlanPanel />);
    fireEvent.change(screen.getByTestId("cgrp-json"), {
      target: { value: "not-json" },
    });
    fireEvent.click(screen.getByTestId("cgrp-build"));
    await waitFor(() => {
      expect(screen.getByTestId("cgrp-error").textContent).toMatch(/JSON|Unexpected/i);
    });
  });
});
