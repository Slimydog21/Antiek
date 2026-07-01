import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { OPERATOR_ROUTES } from "../../shell/operatorRoutes";
import Map from "./index";

afterEach(() => {
  cleanup();
});

describe("Application map", () => {
  it("renders every route in the shared operator route registry", () => {
    render(
      <MemoryRouter>
        <Map />
      </MemoryRouter>,
    );

    for (const route of OPERATOR_ROUTES) {
      expect(screen.getAllByText(route.title).length).toBeGreaterThan(0);
      expect(screen.getAllByText(route.path).length).toBeGreaterThan(0);
    }
  });

  it("labels the meta-reading generator as proposed", () => {
    render(
      <MemoryRouter>
        <Map />
      </MemoryRouter>,
    );

    expect(screen.getByText("Meta-reading")).toBeTruthy();
    expect(screen.getByText("Proposed — sign-off pending")).toBeTruthy();
  });
});
