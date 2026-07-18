import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NotDiamondShadowToggle } from "./NotDiamondShadowToggle";

describe("NotDiamondShadowToggle", () => {
  afterEach(() => cleanup());

  it("starts disabled and never enables live adapter", () => {
    render(<NotDiamondShadowToggle />);
    expect(screen.getByTestId("notdiamond-authority").textContent).toMatch(
      /liveAdapter=false/,
    );
    fireEvent.click(screen.getByTestId("notdiamond-mode-shadow"));
    expect(screen.getByTestId("notdiamond-mode-label").textContent).toMatch(
      /Shadow/i,
    );
    expect(screen.getByTestId("notdiamond-authority").textContent).toMatch(
      /liveAdapter=false/,
    );
    fireEvent.click(screen.getByTestId("notdiamond-mode-advisory"));
    expect(screen.getByTestId("notdiamond-authority").textContent).toMatch(
      /advisory_or_less/,
    );
    expect(screen.getByTestId("notdiamond-authority").textContent).toMatch(
      /liveAdapter=false/,
    );
  });
});
