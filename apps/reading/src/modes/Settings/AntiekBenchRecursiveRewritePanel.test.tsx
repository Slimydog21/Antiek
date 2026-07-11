import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AntiekBenchRecursiveRewritePanel from "./AntiekBenchRecursiveRewritePanel";

afterEach(() => {
  cleanup();
});

describe("AntiekBenchRecursiveRewritePanel", () => {
  it("proposes with applied false", async () => {
    render(
      <AntiekBenchRecursiveRewritePanel initialWeekLabel="2026-W28" />,
    );
    fireEvent.click(screen.getByTestId("abrr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("abrr-applied").textContent).toMatch(/false/);
      expect(screen.getByTestId("abrr-count").textContent).toMatch(
        /proposals=1/,
      );
    });
  });

  it("surfaces validation errors", async () => {
    render(<AntiekBenchRecursiveRewritePanel initialWeekLabel="" />);
    fireEvent.click(screen.getByTestId("abrr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("abrr-error").textContent).toMatch(
        /week_label/,
      );
    });
  });
});
