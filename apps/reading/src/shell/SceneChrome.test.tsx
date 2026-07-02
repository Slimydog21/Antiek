import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { SceneChrome } from "./SceneChrome";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="*"
          element={
            <SceneChrome>
              <LocationProbe />
            </SceneChrome>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("SceneChrome Write actions", () => {
  it("opens the Write start flow instead of creating an unlinked piece in chrome", () => {
    renderAt("/create");

    fireEvent.click(screen.getByRole("button", { name: "New piece" }));

    expect(screen.getByTestId("location").textContent).toBe("/write");
  });
});

describe("SceneChrome Read tabs", () => {
  it("routes Library to the real Read shelf, not the PDF ingest surface", () => {
    renderAt("/read/doc-1");

    fireEvent.click(screen.getByRole("button", { name: "Library" }));

    expect(screen.getByTestId("location").textContent).toBe("/library");
  });
});
