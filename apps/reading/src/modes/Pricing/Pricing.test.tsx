import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import PricingPage from "./index";

afterEach(() => cleanup());

describe("PricingPage", () => {
  it("uses the current Brainstorm station label for private usage", () => {
    render(<PricingPage />);

    expect(
      screen.getByText("Brainstorm station, private documents, private graph."),
    ).toBeTruthy();
    expect(screen.queryByText(/Brainstorming Workstation/)).toBeNull();
  });

  it("ignores malformed calculator inputs instead of rendering invalid money", () => {
    render(<PricingPage />);

    fireEvent.change(screen.getByLabelText("Private tokens per month"), {
      target: { value: "Infinity" },
    });
    fireEvent.change(screen.getByLabelText("Public tokens per month"), {
      target: { value: "NaN" },
    });
    fireEvent.change(
      screen.getByLabelText("Provider raw cost per million tokens"),
      {
        target: { value: "-1" },
      },
    );

    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(screen.getByText("$43.00")).toBeTruthy();
  });

  it("updates the calculator for valid slider values", () => {
    render(<PricingPage />);

    fireEvent.change(screen.getByLabelText("Private tokens per month"), {
      target: { value: "2000000" },
    });
    fireEvent.change(
      screen.getByLabelText("Provider raw cost per million tokens"),
      {
        target: { value: "10" },
      },
    );

    expect(screen.getByText("$20.00")).toBeTruthy();
    expect(screen.getByText("$10.00")).toBeTruthy();
    expect(screen.getByText("$30.00")).toBeTruthy();
  });
});
