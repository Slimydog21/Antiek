import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Map from "./index";

describe("Application map", () => {
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
