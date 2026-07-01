import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import Topbar from "./Topbar";

afterEach(() => {
  cleanup();
});

describe("Topbar", () => {
  it("uses the canonical privacy dashboard breadcrumb label", () => {
    render(
      <MemoryRouter initialEntries={["/privacy"]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText("Privacy dashboard")).toBeTruthy();
    expect(screen.queryByText(/^Privacy$/)).toBeNull();
  });
});
